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
    ReportingContract,
    ReportingContractError,
    ReportLevel,
    is_reportable,
    make_reporting_contract,
    report_error,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from wren_common.reporting_types import SafeContextValue


_log = structlog.get_logger("wren-mcp-reporting")

_MCP_REPORT_LIMITERS = {
    kind.value: ReportLimiter(limit=1, window_seconds=3_600.0)
    for kind in (Kind.UPSTREAM, Kind.TIMEOUT, Kind.INTERNAL)
}


def _validated_contract(
    *,
    operation_name: str,
    kind_name: str,
    log_event_name: str,
    level_name: str,
) -> ReportingContract | None:
    """Validate report metadata before any limiter or capture side effect."""
    try:
        contract = make_reporting_contract(
            operation=operation_name,
            domain=Domain.MCP,
            kind=kind_name,
            log_event=log_event_name,
            level=level_name,
        )
    except ReportingContractError as error:
        _log.warning("reporting_contract_invalid", fields=list(error.fields))
        return None

    # Import lazily because the registrar wraps tool metrics, which imports this
    # reporting adapter.
    from wren_mcp.tool_registry import is_registered_tool

    if contract.operation.startswith("tool.") and not is_registered_tool(
        contract.operation.removeprefix("tool.")
    ):
        _log.warning("reporting_contract_invalid", fields=["operation"])
        return None
    return contract


def report_mcp_error(
    exception: BaseException,
    *,
    operation_name: str,
    kind_name: str,
    log_event_name: str,
    level_name: str,
    user_id: str | None = None,
    bounded_tags: Mapping[str, str] | None = None,
    context_data: Mapping[str, SafeContextValue] | None = None,
    group_key: str | None = None,
) -> None:
    """Send one bounded MCP report without changing the original error path."""
    contract = _validated_contract(
        operation_name=operation_name,
        kind_name=kind_name,
        log_event_name=log_event_name,
        level_name=level_name,
    )
    if contract is None:
        return
    # Backend responses and authorization failures are model-recoverable tool
    # outcomes. They still reach the local tool-failure log, but never create an
    # operational event. BackendToolError marks even 5xx responses explicitly.
    if getattr(exception, "suppress_reporting", False) or not is_reportable(exception):
        return
    limiter = _MCP_REPORT_LIMITERS.get(contract.kind)
    if limiter is not None and not limiter.allow(contract.kind):
        return
    try:
        report_error(
            exception,
            operation=contract.operation,
            domain=Domain.MCP,
            kind=Kind(contract.kind),
            user_id=user_id,
            log_event=LogEvent(contract.log_event),
            level=ReportLevel(contract.level),
            bounded_tags={**dict(bounded_tags or {}), "error_kind": contract.kind},
            context_data={**dict(context_data or {}), "error_kind": contract.kind},
            group_key=f"mcp.{contract.kind}",
            group_exact=True,
        )
    except Exception:  # noqa: BLE001 - reporting must never mask the original error
        _log.warning("error_report_failed", operation=contract.operation, exc_info=True)


__all__ = ["report_mcp_error"]
