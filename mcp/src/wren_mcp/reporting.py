"""MCP adapter for the shared operational error reporter.

The MCP package remains usable with an older workspace checkout while the
shared reporting contract rolls out. Once available, all calls use the typed
``wren_common.reporting.report_error`` boundary. Reporting is best effort and
never replaces the transport, authorization, or tool error that reached it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from wren_common.limiter import ReportLimiter
from wren_common.reporting import (
    Domain,
    Kind,
    LogEvent,
    ReportLevel,
    is_reportable,
    report_error,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


_MCP_REPORT_LIMITERS = {
    kind.value: ReportLimiter(limit=1, window_seconds=3_600.0)
    for kind in (Kind.UPSTREAM, Kind.TIMEOUT, Kind.INTERNAL)
}


def _kind(value: str) -> Kind:
    try:
        return Kind(value)
    except ValueError:
        return Kind.INTERNAL


def _log_event(value: str) -> LogEvent:
    try:
        return LogEvent(value)
    except ValueError:
        return LogEvent.UNHANDLED_EXCEPTION


def report_mcp_error(
    exception: BaseException,
    *,
    operation_name: str,
    kind_name: str,
    log_event_name: str,
    level_name: str,
    user_id: str | None = None,
    bounded_tags: Mapping[str, str] | None = None,
    context_data: Mapping[str, object] | None = None,
    group_key: str | None = None,
) -> None:
    """Send one bounded MCP report without changing the original error path."""
    # Backend responses and authorization failures are model-recoverable tool
    # outcomes. They still reach the local tool-failure log, but never create an
    # operational event. BackendToolError marks even 5xx responses explicitly.
    if getattr(exception, "suppress_reporting", False) or not is_reportable(exception):
        return
    kind = _kind(kind_name)
    limiter = _MCP_REPORT_LIMITERS.get(kind.value)
    if limiter is not None and not limiter.allow(kind.value):
        return
    try:
        report_error(
            exception,
            operation=operation_name,
            domain=Domain.MCP,
            kind=kind,
            user_id=user_id,
            log_event=_log_event(log_event_name),
            level=ReportLevel(level_name),
            bounded_tags={**dict(bounded_tags or {}), "error_kind": kind.value},
            context_data={**dict(context_data or {}), "error_kind": kind.value},
            group_key=f"mcp.{kind.value}",
            group_exact=True,
        )
    except Exception:  # noqa: BLE001 - reporting must never mask the original error
        structlog.get_logger("wren-mcp").warning(
            "error_report_failed", operation=operation_name, exc_info=True
        )


__all__ = ["report_mcp_error"]
