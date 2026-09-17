"""Sentry initialization and exception reporting shared by both deployables."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import sentry_sdk

from wren_common.limiter import EventLimiter
from wren_common.logging import get_logger
from wren_common.reporting import (
    ReportCategory,
    category_value,
    classify_exception,
    exception_kind,
)
from wren_common.reporting_types import sanitize_context, sanitize_tags

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sentry_sdk.types import Event

_initialized = False
_disabled_logged = False
_disabled_services: set[str] = set()
_REPORT_LIMITER = EventLimiter(limit=20, window_seconds=60)
_REDACTED_EXCEPTION = "[Redacted exception]"


def _scrub_event(event: Event, _hint: dict[str, Any]) -> Event:
    """Remove request-derived payloads while preserving exception types and frames."""
    event_data = cast("dict[str, Any]", event)
    for field in ("request", "breadcrumbs", "extra", "message", "logentry"):
        event_data.pop(field, None)
    contexts = event_data.get("contexts")
    if isinstance(contexts, dict):
        event_data["contexts"] = {"report": contexts["report"]} if "report" in contexts else {}
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


_RELEASE_PREFIXES = {
    "wren": "wren-backend",
    "wren-external": "wren-backend",
    "wren-internal": "wren-backend",
    "wren-mcp": "wren-mcp",
}


def _release_name(release: str, service: str) -> str | None:
    value = release.strip()
    if not value:
        return None
    prefix = _RELEASE_PREFIXES.get(service)
    if prefix is None:
        raise ValueError(f"unsupported Sentry service: {service}")

    if "@" in value:
        supplied_prefix, _, value = value.partition("@")
        if supplied_prefix != prefix or not value or "@" in value:
            raise ValueError(f"release must use the {prefix}@<version> format")
    return f"{prefix}@{value}"


def initialize_sentry(
    *,
    dsn: str,
    environment: str,
    release: str,
    service: str = "wren",
    logger: Any | None = None,
) -> bool:
    """Initialize Sentry once when a DSN is configured.

    A blank DSN disables reporting and does not lock out a later configured app
    in the same test or process. Sentry SDK initialization stays after logging
    setup in each app factory so startup diagnostics use the configured logger.
    """
    global _disabled_logged, _initialized
    log = logger or get_logger(service)
    if _initialized:
        return False
    if not dsn.strip():
        if service not in _disabled_services:
            log.info("sentry_disabled", reason="dsn_not_configured")
            _disabled_services.add(service)
            _disabled_logged = True
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=_release_name(release, service),
        send_default_pii=False,
        before_send=_scrub_event,
        integrations=[],
        traces_sample_rate=0.0,
    )
    _initialized = True
    log.info("sentry_initialized", environment=environment, release=release or None)
    return True


def report_exception(
    exception: BaseException,
    *,
    category: ReportCategory | str | None = None,
    limiter: EventLimiter | None = _REPORT_LIMITER,
    tags: Mapping[str, str] | None = None,
    context: Mapping[str, Any] | None = None,
    fingerprint: list[str] | None = None,
    user_id: str | None = None,
) -> str | None:
    """Capture one unexpected exception and return its Sentry event id.

    Expected errors are ignored by default. A caller can supply a category when
    it has a more precise classification than the shared HTTP-status rule.
    ``limiter`` keys on exception type, avoiding secret-bearing exception text.
    """
    resolved_category = (
        classify_exception(exception) if category is None else category_value(category)
    )
    if category_value(resolved_category) == ReportCategory.EXPECTED.value:
        return None

    if limiter is not None and not limiter.allow(type(exception).__qualname__):
        return None

    safe_tags = sanitize_tags(tags)
    safe_tags["report_category"] = category_value(resolved_category)
    safe_tags["error_kind"] = exception_kind(exception)
    safe_context = sanitize_context(context)
    with sentry_sdk.new_scope() as scope:
        for key, value in safe_tags.items():
            scope.set_tag(key, value)
        if safe_context:
            scope.set_context("report", safe_context)
        if user_id:
            scope.set_user({"id": user_id})
        if fingerprint:
            scope.fingerprint = fingerprint
        return sentry_sdk.capture_exception(exception)


# Explicit alias for code that names the sink rather than the action.
capture_exception = report_exception
