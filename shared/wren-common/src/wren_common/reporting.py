"""Safe, low-cardinality error reporting shared by both deployables."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from wren_common.logging import get_logger
from wren_common.reporting_types import (
    BoundedTags,
    Domain,
    GroupKey,
    Kind,
    LogEvent,
    Operation,
    ReportLevel,
    SafeContext,
    sanitize_context,
    sanitize_tags,
)


class ReportCategory(StrEnum):
    EXPECTED = "expected"
    UNEXPECTED = "unexpected"


ReportClass = ReportCategory


def exception_kind(exception: BaseException) -> str:
    """Return a bounded exception type name suitable for a Sentry tag."""
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
    return category.value if isinstance(category, ReportCategory) else str(category)


_OPERATION_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_OPERATION_DOMAINS = {
    "accounts",
    "db",
    "oauth",
    "progress",
    "roadmaps",
    "skill",
}


@dataclass(frozen=True, slots=True)
class ReportingContract:
    operation: str
    domain: str | None
    kind: str
    log_event: str
    level: str


class ReportingContractError(ValueError):
    def __init__(self, fields: tuple[str, ...]) -> None:
        super().__init__("invalid reporting contract")
        self.fields = fields


def _value(value: object) -> str:
    if isinstance(value, StrEnum):
        return value.value
    return value if isinstance(value, str) else ""


def _valid_enum(value: StrEnum | str, enum: type[StrEnum]) -> str | None:
    candidate = _value(value)
    return candidate if candidate in {member.value for member in enum} else None


def _operation(value: Operation | str) -> str:
    return _value(value)


def make_reporting_contract(
    *,
    operation: Operation | str,
    domain: Domain | str | None,
    kind: Kind | str,
    log_event: LogEvent | str,
    level: ReportLevel | str,
) -> ReportingContract:
    """Create a validated reporting contract from runtime values."""
    invalid: list[str] = []
    normalized_operation = _operation(operation)
    normalized_domain = None if domain is None else _valid_enum(domain, Domain)
    normalized_kind = _valid_enum(kind, Kind)
    normalized_event = _valid_enum(log_event, LogEvent)
    normalized_level = _valid_enum(level, ReportLevel)

    if not _OPERATION_RE.fullmatch(normalized_operation):
        invalid.append("operation")
    if domain is not None and normalized_domain is None:
        invalid.append("domain")
    if normalized_kind is None:
        invalid.append("kind")
    if normalized_event is None:
        invalid.append("log_event")
    if normalized_level is None:
        invalid.append("level")

    if normalized_operation == "http.500":
        if normalized_domain is not None:
            invalid.append("domain")
    elif normalized_domain is None:
        invalid.append("domain")
    else:
        prefix = normalized_operation.split(".", 1)[0]
        valid_prefix = prefix == normalized_domain or (
            normalized_domain == Domain.MCP.value and prefix in {"mcp", "tool"}
        )
        if prefix not in _OPERATION_DOMAINS and not (
            normalized_domain == Domain.MCP.value and prefix in {"mcp", "tool"}
        ):
            valid_prefix = False
        if not valid_prefix:
            invalid.append("operation")
            invalid.append("domain")

    if invalid:
        raise ReportingContractError(tuple(dict.fromkeys(invalid)))
    return ReportingContract(
        operation=normalized_operation,
        domain=normalized_domain,
        kind=normalized_kind or "",
        log_event=normalized_event or "",
        level=normalized_level or "",
    )


# Factory spelling used by integrations that prefer a create_* convention.
create_reporting_contract = make_reporting_contract


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
        )
    except ReportingContractError as error:
        log.warning("reporting_contract_invalid", fields=list(error.fields))
        return

    normalized_group = _operation(group_key or contract.operation)
    if not _OPERATION_RE.fullmatch(normalized_group):
        normalized_group = contract.operation
    tags = sanitize_tags(bounded_tags)
    tags.update(
        {
            "operation": contract.operation,
            "kind": contract.kind,
            "log_event": contract.log_event,
            "level": contract.level,
            "error_kind": exception_kind(exception),
        }
    )
    if contract.domain is not None:
        tags["domain"] = contract.domain

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

    report_exception(
        exception,
        limiter=None,
        tags=tags,
        context=context,
        fingerprint=([normalized_group] if group_exact else [normalized_group, "{{ default }}"]),
        user_id=user_id,
    )


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
