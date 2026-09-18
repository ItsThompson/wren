"""Safe, low-cardinality error reporting shared by both deployables."""

from __future__ import annotations

from typing import Any

from wren_common.logging import get_logger
from wren_common.reporting_contract import (
    ReportingContract,
    ReportingContractError,
    build_report_fingerprint,
    create_reporting_contract,
    make_reporting_contract,
)
from wren_common.reporting_types import (
    BoundedTags,
    Domain,
    GroupKey,
    Kind,
    LogEvent,
    Operation,
    ReportCategory,
    ReportLevel,
    SafeContext,
    sanitize_context,
    sanitize_tags,
)

ReportClass = ReportCategory


def exception_kind(exception: BaseException) -> str:
    """Return a bounded exception type name for local diagnostics."""
    name = type(exception).__name__
    return name[:200] if name else "BaseException"


def classify_exception(exception: BaseException) -> ReportCategory:
    status = getattr(exception, "status", None)
    if isinstance(status, int) and not isinstance(status, bool) and status < 500:
        return ReportCategory.EXPECTED
    return ReportCategory.UNEXPECTED


def is_reportable(exception: BaseException) -> bool:
    return classify_exception(exception) is ReportCategory.UNEXPECTED


def category_value(category: ReportCategory | str) -> str:
    if isinstance(category, ReportCategory):
        return category.value
    if type(category) is not str:
        return ""
    try:
        return ReportCategory(category).value
    except ValueError:
        return ""


def report_error(
    exception: BaseException,
    *,
    operation: Operation | str,
    domain: Domain | str | None,
    kind: Kind | str,
    user_id: str | None,
    log_event: LogEvent | str,
    level: ReportLevel | str,
    bounded_tags: BoundedTags | None,
    context_data: SafeContext | None,
    group_key: GroupKey | str | None,
    group_exact: bool,
    registered_tools: frozenset[str] | None = None,
    logger: Any | None = None,
) -> None:
    """Report one operational exception without changing request behavior."""
    from wren_common.sentry import report_exception

    log = logger or get_logger("wren-reporting")
    try:
        contract = make_reporting_contract(
            operation=operation,
            domain=domain,
            kind=kind,
            log_event=log_event,
            level=level,
            registered_tools=registered_tools,
        )
    except ReportingContractError as error:
        log.error(LogEvent.UNHANDLED_EXCEPTION.value, exc_info=exception)
        log.warning("reporting_contract_invalid", fields=list(error.fields))
        return

    caller_tags = sanitize_tags(bounded_tags)
    caller_tags.pop("tool", None)
    if contract.domain == Domain.MCP.value and contract.operation.startswith("tool."):
        caller_tags["tool"] = contract.operation.removeprefix("tool.")
    reporter_tags = {
        "operation": contract.operation,
        "kind": contract.kind,
        "log_event": contract.log_event,
        "level": contract.level,
        "error_kind": contract.kind,
    }
    if contract.domain is not None:
        reporter_tags["domain"] = contract.domain
    tags = {**caller_tags, **reporter_tags}

    context = sanitize_context(context_data)
    log_method = getattr(log, contract.level)
    log_fields: dict[str, object] = {
        key: value for key, value in tags.items() if key not in {"operation", "domain", "kind"}
    }
    log_fields.update(
        {
            "operation": contract.operation,
            "domain": contract.domain,
            "kind": contract.kind,
            **{key: value for key, value in context.items() if key not in log_fields},
            "exc_info": exception,
        }
    )
    log_method(contract.log_event, **log_fields)

    fingerprint = build_report_fingerprint(
        contract,
        group_key=group_key,
        group_exact=group_exact,
    )
    if fingerprint is None:
        log.warning("reporting_group_invalid", fields=["group_key"])
        return

    try:
        report_exception(
            exception,
            limiter=None,
            tags=caller_tags,
            context=context,
            fingerprint=fingerprint,
            user_id=user_id,
            error_kind=contract.kind,
            reporter_tags=reporter_tags,
            level=contract.level,
        )
    except Exception:  # noqa: BLE001 - reporting never changes application behavior
        log.warning("error_report_failed", operation=contract.operation)


__all__ = [
    "BoundedTags",
    "Domain",
    "GroupKey",
    "Kind",
    "LogEvent",
    "Operation",
    "ReportCategory",
    "ReportClass",
    "ReportLevel",
    "ReportingContract",
    "ReportingContractError",
    "SafeContext",
    "category_value",
    "classify_exception",
    "create_reporting_contract",
    "exception_kind",
    "is_reportable",
    "make_reporting_contract",
    "report_error",
]
