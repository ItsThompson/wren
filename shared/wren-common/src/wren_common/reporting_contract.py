"""Runtime validation for bounded reporting identity and grouping."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from wren_common.reporting_types import Domain, GroupKey, Kind, LogEvent, Operation, ReportLevel

if TYPE_CHECKING:
    from collections.abc import Callable
    from enum import StrEnum


_OPERATION_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")


def _enum_value(value: object, enum: type[StrEnum]) -> str | None:
    if isinstance(value, enum):
        return value.value
    if type(value) is not str:
        return None
    try:
        return enum(value).value
    except ValueError:
        return None


def _registered_operation_factory(*operations: str) -> Callable[[str, frozenset[str] | None], bool]:
    registered = frozenset(operations)

    def is_registered(operation: str, _registered_tools: frozenset[str] | None) -> bool:
        return operation in registered

    return is_registered


_OPERATION_FACTORIES: dict[str, Callable[[str, frozenset[str] | None], bool]] = {
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
}

_FIXED_MCP_OPERATIONS = frozenset({"mcp.backend_error", "mcp.internal_request"})


def _mcp_operation_is_registered(operation: str, registered_tools: frozenset[str] | None) -> bool:
    if operation in _FIXED_MCP_OPERATIONS:
        return True
    if operation.startswith("tool."):
        return registered_tools is not None and operation.removeprefix("tool.") in registered_tools
    return False


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
    registered_tools: frozenset[str] | None = None,
) -> ReportingContract:
    """Create a validated reporting contract from runtime values.

    ``registered_tools`` is the closed MCP tool identity set. Tool operations
    (``tool.<name>``) validate only against it; passing ``None`` rejects every
    tool operation.
    """
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
        if normalized_domain == Domain.MCP.value:
            if not _mcp_operation_is_registered(normalized_operation, registered_tools):
                invalid.append("operation")
        else:
            operation_factory = _OPERATION_FACTORIES[normalized_domain]
            if not operation_factory(normalized_operation, registered_tools):
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


create_reporting_contract = make_reporting_contract


def build_report_fingerprint(
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
    if normalized_group == contract.operation:
        return [contract.operation, contract.kind, "{{ default }}"]
    return [normalized_group, "{{ default }}"]
