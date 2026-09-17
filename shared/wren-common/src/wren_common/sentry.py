"""Sentry initialization and exception reporting shared by both deployables."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import sentry_sdk

from wren_common.limiter import EventLimiter
from wren_common.logging import get_logger
from wren_common.reporting import ReportCategory, category_value, classify_exception

if TYPE_CHECKING:
    from collections.abc import Mapping

_initialized = False
_disabled_logged = False
_REPORT_LIMITER = EventLimiter(limit=20, window_seconds=60)


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
        if not _disabled_logged:
            log.info("sentry_disabled", reason="dsn_not_configured")
            _disabled_logged = True
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release or None,
        send_default_pii=False,
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

    with sentry_sdk.push_scope() as scope:
        scope.set_tag("report_category", category_value(resolved_category))
        if tags:
            for key, value in tags.items():
                scope.set_tag(key, value)
        if context:
            scope.set_context("report", dict(context))
        if user_id:
            scope.set_user({"id": user_id})
        if fingerprint:
            scope.fingerprint = fingerprint
        return sentry_sdk.capture_exception(exception)


# Explicit alias for code that names the sink rather than the action.
capture_exception = report_exception
