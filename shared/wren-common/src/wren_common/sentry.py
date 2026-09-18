"""Sentry initialization and exception reporting shared by both deployables."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, cast

import sentry_sdk

from wren_common.limiter import EventLimiter
from wren_common.logging import get_logger
from wren_common.reporting import classify_exception
from wren_common.reporting_types import (
    BoundedTags,
    Kind,
    ReportCategory,
    ReportLevel,
    SafeContext,
    sanitize_context,
    sanitize_tags,
)
from wren_common.sentry_scrub import (
    REPORT_CONTEXT_MARKER_TAG as _REPORT_CONTEXT_MARKER_TAG,
)
from wren_common.sentry_scrub import REPORT_MARKER_TAG as _REPORT_MARKER_TAG
from wren_common.sentry_scrub import REPORT_TAG_KEYS_TAG as _REPORT_TAG_KEYS_TAG
from wren_common.sentry_scrub import REPORT_USER_MARKER_TAG as _REPORT_USER_MARKER_TAG
from wren_common.sentry_scrub import sanitize_reporter_tags as _sanitize_reporter_tags
from wren_common.sentry_scrub import scrub_event

if TYPE_CHECKING:
    from sentry_sdk.transport import Transport

_scrub_event = scrub_event
_initialized = False
_disabled_logged = False
_disabled_services: set[str] = set()
# Process-wide service identity, set once by the enabled initialize_sentry call.
# Every isolated report scope receives it as the ``service`` tag so external,
# internal, and MCP events stay distinguishable inside one Sentry project.
_SERVICE: str | None = None
_REPORT_LIMITER = EventLimiter(limit=20, window_seconds=60)


def _normalize_level(value: ReportLevel | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, ReportLevel):
        return value.value
    if type(value) is not str:
        return None
    try:
        return ReportLevel(value).value
    except ValueError:
        return None


_DEPLOY_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_RELEASE_PREFIXES = {
    "wren": "wren-api",
    "wren-external": "wren-api",
    "wren-internal": "wren-api",
    "wren-mcp": "wren-mcp",
}


def _release_name(release: str, service: str) -> str | None:
    value = release.strip()
    if not value:
        return None
    prefix = _RELEASE_PREFIXES.get(service)
    if prefix is None:
        raise ValueError(f"unsupported Sentry service: {service}")

    if _DEPLOY_SHA_RE.fullmatch(value) is None:
        raise ValueError("release must be a bare 40-character lowercase hexadecimal SHA")
    return f"{prefix}@{value}"


def initialize_sentry(
    *,
    dsn: str,
    environment: str,
    release: str,
    service: str = "wren",
    logger: Any | None = None,
    transport: Transport | None = None,
) -> bool:
    """Initialize Sentry once when a DSN is configured.

    A blank DSN disables reporting and does not lock out a later configured app
    in the same test or process. Sentry SDK initialization stays after logging
    setup in each app factory so startup diagnostics use the configured logger.
    ``transport`` lets tests install a recording transport; production callers
    leave it unset so the SDK's own HTTP transport is used.
    """
    global _disabled_logged, _initialized, _SERVICE
    log = logger or get_logger(service)
    if _initialized:
        return False
    if not dsn.strip():
        if service not in _disabled_services:
            log.info("sentry_disabled", reason="dsn_not_configured")
            _disabled_services.add(service)
            _disabled_logged = True
        return False

    options: dict[str, Any] = {
        "dsn": dsn,
        "environment": environment,
        "release": _release_name(release, service),
        "send_default_pii": False,
        "before_send": _scrub_event,
        "default_integrations": False,
        "integrations": [],
        "propagate_traces": False,
        "traces_sample_rate": None,
        "max_breadcrumbs": 0,
    }
    if transport is not None:
        options["transport"] = transport
    sentry_sdk.init(**options)
    _initialized = True
    _SERVICE = service
    log.info("sentry_initialized", environment=environment, release=release or None)
    return True


def report_exception(
    exception: BaseException,
    *,
    category: ReportCategory | str | None = None,
    limiter: EventLimiter | None = _REPORT_LIMITER,
    tags: BoundedTags | None = None,
    context: SafeContext | None = None,
    fingerprint: list[str] | None = None,
    user_id: str | None = None,
    error_kind: Kind | str | None = None,
    reporter_tags: dict[str, str] | None = None,
    level: ReportLevel | str | None = None,
) -> str | None:
    """Capture one unexpected exception and return its Sentry event id.

    Expected errors are ignored by default. A caller can supply a category when
    it has a more precise classification than the shared HTTP-status rule.
    ``limiter`` keys on exception type, avoiding secret-bearing exception text.
    """
    if category is None:
        resolved_category = classify_exception(exception)
    elif isinstance(category, ReportCategory):
        resolved_category = category
    elif type(category) is str:
        try:
            resolved_category = ReportCategory(category)
        except ValueError:
            return None
    else:
        return None
    if resolved_category is ReportCategory.EXPECTED:
        return None

    if limiter is not None and not limiter.allow(type(exception).__qualname__):
        return None

    safe_tags = sanitize_tags(tags)
    owned_tags = _sanitize_reporter_tags(reporter_tags)
    safe_tags.update(owned_tags)
    safe_tags["report_category"] = resolved_category.value
    if error_kind is None:
        normalized_error_kind = Kind.INTERNAL.value
    elif isinstance(error_kind, Kind):
        normalized_error_kind = error_kind.value
    elif type(error_kind) is str:
        try:
            normalized_error_kind = Kind(error_kind).value
        except ValueError:
            return None
    else:
        return None
    safe_tags["error_kind"] = normalized_error_kind
    normalized_level = _normalize_level(level if level is not None else owned_tags.get("level"))
    if level is not None and normalized_level is None:
        return None
    safe_context = sanitize_context(context)
    with sentry_sdk.new_scope() as scope:
        scope.clear()
        scope.set_tag(_REPORT_MARKER_TAG, "1")
        owned_tag_keys = set(safe_tags)
        if _SERVICE is not None:
            owned_tag_keys.add("service")
        scope.set_tag(_REPORT_TAG_KEYS_TAG, ",".join(sorted(owned_tag_keys)))
        scope.set_tag(_REPORT_CONTEXT_MARKER_TAG, "1" if safe_context else "0")
        scope.set_tag(_REPORT_USER_MARKER_TAG, "1" if user_id else "0")
        for key, value in safe_tags.items():
            scope.set_tag(key, value)
        if _SERVICE is not None:
            scope.set_tag("service", _SERVICE)
        if normalized_level is not None:
            scope.set_level(cast("Any", normalized_level))
        if safe_context:
            scope.set_context("report", safe_context)
        if user_id:
            scope.set_user({"id": user_id})
        if fingerprint:
            scope.fingerprint = fingerprint
        return sentry_sdk.capture_exception(exception)


# Explicit alias for code that names the sink rather than the action.
capture_exception = report_exception
