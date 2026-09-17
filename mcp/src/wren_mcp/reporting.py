"""MCP adapter for the shared operational error reporter.

The MCP package remains usable with an older workspace checkout while the
shared reporting contract rolls out. Once available, all calls use the typed
``wren_common.reporting.report_error`` boundary. Reporting is best effort and
never replaces the transport, authorization, or tool error that reached it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from wren_common.reporting import (
    Domain,
    Kind,
    LogEvent,
    ReportLevel,
    report_error,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


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
    """Send a typed MCP report without changing the original error path."""
    try:
        report_error(
            exception,
            operation=operation_name,
            domain=Domain.MCP,
            kind=_kind(kind_name),
            user_id=user_id,
            log_event=_log_event(log_event_name),
            level=ReportLevel(level_name),
            bounded_tags=dict(bounded_tags or {}),
            context_data=dict(context_data or {}),
            group_key=group_key or operation_name,
            group_exact=True,
        )
    except Exception:  # noqa: BLE001 - reporting must never mask the original error
        structlog.get_logger("wren-mcp").warning(
            "error_report_failed", operation=operation_name, exc_info=True
        )


__all__ = ["report_mcp_error"]
