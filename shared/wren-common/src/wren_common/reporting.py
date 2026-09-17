"""Safe, low-cardinality error reporting shared by both deployables."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from wren_common.logging import get_logger
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

if TYPE_CHECKING:
    from collections.abc import Callable
    from enum import StrEnum


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


def _enum_value(value: object, enum: type[StrEnum]) -> str | None:
    if isinstance(value, enum):
        return value.value
    if type(value) is not str:
        return None
    try:
        return enum(value).value
    except ValueError:
        return None


def category_value(category: ReportCategory | str) -> str:
    normalized = _enum_value(category, ReportCategory)
    return normalized if normalized is not None else ""


_OPERATION_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_TOOL_OPERATION_RE = re.compile(r"^tool\.[a-z][a-z0-9_]{0,127}$")


def _registered_operation_factory(*operations: str) -> Callable[[str], bool]:
    registered = frozenset(operations)

    def is_registered(operation: str) -> bool:
        return operation in registered

    return is_registered


_OPERATION_FACTORIES: dict[str, Callable[[str], bool]] = {
    Domain.ACCOUNTS.value: _registered_operation_factory(
        "accounts.register",
        "accounts.login",
        "accounts.refresh",
        "accounts.logout",
        "accounts.complete_onboarding",
        "accounts.profile",
    ),
    Domain.DB.value: _registered_operation_factory(),
    Domain.OAUTH.value: _registered_operation_factory(
        "oauth.metadata",
        "oauth.jwks",
        "oauth.register_client",
        "oauth.authorize",
        "oauth.authorize_context",
        "oauth.authorize_decision",
        "oauth.token",
        "oauth.revoke",
        "oauth.list_clients",
        "oauth.revoke_client",
        "oauth.cleanup",
    ),
    Domain.PROGRESS.value: _registered_operation_factory(
        "progress.follow",
        "progress.get",
        "progress.update",
        "progress.next",
        "progress.deadline",
    ),
    Domain.ROADMAPS.value: _registered_operation_factory(
        "roadmaps.create",
        "roadmaps.get",
        "roadmaps.patch",
        "roadmaps.replace",
        "roadmaps.validate",
        "roadmaps.publish",
        "roadmaps.fork",
        "roadmaps.edit_metadata",
        "roadmaps.overview",
        "roadmaps.node",
        "roadmaps.section",
        "roadmaps.search",
        "roadmaps.published_visibility",
        "roadmaps.archive",
        "roadmaps.delete",
        "roadmaps.dashboard",
    ),
    Domain.SKILL.value: _registered_operation_factory("skill.get"),
    Domain.MCP.value: lambda operation: (
        operation
        in {
            "mcp.backend_error",
            "mcp.internal_request",
        }
        or bool(_TOOL_OPERATION_RE.fullmatch(operation))
    ),
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


def _operation(value: Operation | str) -> str:
    return value if type(value) is str else ""


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
    normalized_domain = None if domain is None else _enum_value(domain, Domain)
    normalized_kind = _enum_value(kind, Kind)
    normalized_event = _enum_value(log_event, LogEvent)
    normalized_level = _enum_value(level, ReportLevel)

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
        operation_factory = _OPERATION_FACTORIES[normalized_domain]
        if not operation_factory(normalized_operation):
            invalid.append("operation")
        prefix = normalized_operation.split(".", 1)[0]
        if not (
            prefix == normalized_domain
            or (normalized_domain == Domain.MCP.value and prefix in {"mcp", "tool"})
        ):
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


def _report_fingerprint(
    contract: ReportingContract,
    *,
    group_key: GroupKey | str | None,
    group_exact: bool,
) -> list[str] | None:
    """Build a bounded fingerprint without accepting request identity values."""
    if group_key is None:
        normalized_group = contract.operation
    else:
        normalized_group = _operation(group_key)
        if not _OPERATION_RE.fullmatch(normalized_group):
            return None

    exact_group = (
        contract.operation == "oauth.cleanup"
        and normalized_group == f"oauth.cleanup.{contract.kind}"
    ) or (contract.domain == Domain.MCP.value and normalized_group == f"mcp.{contract.kind}")
    if group_exact is True and exact_group:
        return [normalized_group]
    if normalized_group != contract.operation and not exact_group:
        return None
    if group_exact is True and normalized_group != contract.operation:
        return None

    # Backend adapters pass the operation as their group key. Treat that value
    # as the default grouping and include the error kind.
    if normalized_group == contract.operation:
        return [contract.operation, contract.kind, "{{ default }}"]
    return [normalized_group, "{{ default }}"]


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

    tags = sanitize_tags(bounded_tags)
    tags.update(
        {
            "operation": contract.operation,
            "kind": contract.kind,
            "log_event": contract.log_event,
            "level": contract.level,
            "error_kind": contract.kind,
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

    fingerprint = _report_fingerprint(
        contract,
        group_key=group_key,
        group_exact=group_exact,
    )
    if fingerprint is None:
        log.warning("reporting_group_invalid", fields=["group_key"])
        return

    report_exception(
        exception,
        limiter=None,
        tags=tags,
        context=context,
        fingerprint=fingerprint,
        user_id=user_id,
        error_kind=contract.kind,
        reporter_tags=tags,
        level=contract.level,
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
