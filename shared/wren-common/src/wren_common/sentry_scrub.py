"""Closed, reporter-owned privacy filtering for Python Sentry envelopes."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, cast

from wren_common.reporting_types import (
    MAX_TAG_VALUE_LENGTH,
    BoundedTags,
    Domain,
    Kind,
    LogEvent,
    ReportCategory,
    ReportLevel,
    SafeContext,
    sanitize_context,
    sanitize_tags,
)

if TYPE_CHECKING:
    from enum import StrEnum

    from sentry_sdk.types import Event

REPORT_MARKER_TAG = "_wren_report"
REPORT_TAG_KEYS_TAG = "_wren_tag_keys"
REPORT_CONTEXT_MARKER_TAG = "_wren_context"
REPORT_USER_MARKER_TAG = "_wren_user"
_REDACTED_EXCEPTION = "[Redacted exception]"
_OPERATION_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_REPORTER_TAG_ENUMS: dict[str, type[StrEnum]] = {
    "domain": Domain,
    "kind": Kind,
    "log_event": LogEvent,
    "level": ReportLevel,
}
_SERVICE_TAG_VALUES = frozenset({"wren", "wren-external", "wren-internal", "wren-mcp"})


def _normalized_enum_tag(value: object, enum_type: type[StrEnum]) -> str | None:
    if type(value) is not str:
        return None
    try:
        return enum_type(value).value
    except ValueError:
        return None


def sanitize_reporter_tags(value: dict[str, Any] | None) -> dict[str, str]:
    if not value:
        return {}
    result: dict[str, str] = {}
    operation = value.get("operation")
    if type(operation) is str and _OPERATION_RE.fullmatch(operation):
        result["operation"] = operation
    for key, enum_type in _REPORTER_TAG_ENUMS.items():
        normalized = _normalized_enum_tag(value.get(key), enum_type)
        if normalized is not None:
            result[key] = normalized
    return result


def scrub_event(event: Event, _hint: dict[str, Any]) -> Event:
    """Keep only reporter-owned, bounded event metadata and safe stack data."""
    event_data = cast("dict[str, Any]", event)
    for field in ("request", "breadcrumbs", "extra", "message", "logentry"):
        event_data.pop(field, None)

    raw_tags = event_data.get("tags")
    reporter_event = isinstance(raw_tags, dict) and raw_tags.get(REPORT_MARKER_TAG) == "1"
    owned_tag_keys: frozenset[str] = frozenset()
    safe_tags: dict[str, str] = {}
    if reporter_event and isinstance(raw_tags, dict):
        raw_owned_tag_keys = raw_tags.get(REPORT_TAG_KEYS_TAG)
        if type(raw_owned_tag_keys) is str:
            owned_tag_keys = frozenset(raw_owned_tag_keys.split(","))
        safe_tags.update(sanitize_tags(cast("BoundedTags", raw_tags)))
        safe_tags.update(sanitize_reporter_tags(raw_tags))
        report_category = _normalized_enum_tag(raw_tags.get("report_category"), ReportCategory)
        error_kind = _normalized_enum_tag(raw_tags.get("error_kind"), Kind)
        service = raw_tags.get("service")
        if report_category is not None:
            safe_tags["report_category"] = report_category
        if error_kind is not None:
            safe_tags["error_kind"] = error_kind
        if type(service) is str and service in _SERVICE_TAG_VALUES:
            safe_tags["service"] = service
    event_data["tags"] = {key: value for key, value in safe_tags.items() if key in owned_tag_keys}

    contexts = event_data.get("contexts")
    report_context: dict[str, Any] | None = None
    owns_context = (
        reporter_event
        and isinstance(raw_tags, dict)
        and raw_tags.get(REPORT_CONTEXT_MARKER_TAG) == "1"
    )
    if owns_context and isinstance(contexts, dict):
        raw_report_context = contexts.get("report")
        if isinstance(raw_report_context, dict):
            report_context = sanitize_context(cast("SafeContext", raw_report_context))
    event_data["contexts"] = {"report": report_context} if report_context else {}

    user = event_data.get("user")
    owns_user = (
        reporter_event
        and isinstance(raw_tags, dict)
        and raw_tags.get(REPORT_USER_MARKER_TAG) == "1"
    )
    user_id = user.get("id") if owns_user and isinstance(user, dict) else None
    if type(user_id) is str and user_id and len(user_id.encode("utf-8")) <= MAX_TAG_VALUE_LENGTH:
        event_data["user"] = {"id": user_id}
    else:
        event_data.pop("user", None)

    exception = event_data.get("exception")
    if isinstance(exception, dict):
        values = exception.get("values")
        if isinstance(values, list):
            for value in values:
                if not isinstance(value, dict):
                    continue
                value["value"] = _REDACTED_EXCEPTION
                value.pop("mechanism", None)
                stacktrace = value.get("stacktrace")
                if isinstance(stacktrace, dict):
                    frames = stacktrace.get("frames")
                    if isinstance(frames, list):
                        for frame in frames:
                            if isinstance(frame, dict):
                                frame.pop("vars", None)
    return event
