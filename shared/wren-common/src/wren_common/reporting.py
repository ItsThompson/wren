"""Safe, low-cardinality error reporting shared by both deployables."""

from __future__ import annotations

import re
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
)


class ReportCategory(StrEnum):
    EXPECTED = "expected"
    UNEXPECTED = "unexpected"


ReportClass = ReportCategory


def classify_exception(exception: BaseException) -> ReportCategory:
    status = getattr(exception, "status", None)
    if isinstance(status, int) and status < 500:
        return ReportCategory.EXPECTED
    return ReportCategory.UNEXPECTED


def is_reportable(exception: BaseException) -> bool:
    return classify_exception(exception) is ReportCategory.UNEXPECTED


def category_value(category: ReportCategory | str) -> str:
    return category.value if isinstance(category, ReportCategory) else str(category)


_OPERATION_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_MAX_VALUE_LENGTH = 256


def _value(value: StrEnum | str) -> str:
    return value.value if isinstance(value, StrEnum) else value


def _valid_enum(value: StrEnum | str, enum: type[StrEnum]) -> str | None:
    candidate = _value(value)
    return candidate if candidate in {member.value for member in enum} else None


def _bounded_mapping(value: BoundedTags | SafeContext | None) -> dict[str, object]:
    if not value:
        return {}
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or len(key) > _MAX_VALUE_LENGTH:
            continue
        if isinstance(item, str):
            result[key] = item[:_MAX_VALUE_LENGTH]
        elif isinstance(item, (bool, int, float)) or item is None:
            result[key] = item
    return result


def _operation(value: Operation | str) -> str:
    candidate = _value(value)
    return candidate if _OPERATION_RE.fullmatch(candidate) else "http.500"


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
    """Report one operational exception without changing request behavior.

    Invalid taxonomy values are dropped rather than reaching Sentry. Operation
    identity is the one exception: malformed values use the safe ``http.500``
    fallback so an unclassified failure still has a stable grouping key.
    """
    from wren_common.sentry import report_exception

    normalized_domain = None if domain is None else _valid_enum(domain, Domain)
    normalized_kind = _valid_enum(kind, Kind)
    normalized_event = _valid_enum(log_event, LogEvent)
    normalized_level = _valid_enum(level, ReportLevel)
    if (domain is not None and normalized_domain is None) or normalized_kind is None:
        return
    if normalized_event is None or normalized_level is None:
        return

    normalized_operation = _operation(operation)
    normalized_group = _operation(group_key or normalized_operation)
    tags = _bounded_mapping(bounded_tags)
    tags.update(
        {
            "operation": normalized_operation,
            "kind": normalized_kind,
            "log_event": normalized_event,
            "level": normalized_level,
        }
    )
    if normalized_domain is not None:
        tags["domain"] = normalized_domain

    context = _bounded_mapping(context_data)
    log = logger or get_logger("wren-reporting")
    log_method = getattr(log, normalized_level)
    log_fields: dict[str, object] = {
        key: value for key, value in tags.items() if key not in {"operation", "domain", "kind"}
    }
    log_fields.update(
        {
            "operation": normalized_operation,
            "domain": normalized_domain,
            "kind": normalized_kind,
            **{key: value for key, value in context.items() if key not in log_fields},
            "exc_info": exception,
        }
    )
    log_method(normalized_event, **log_fields)

    report_exception(
        exception,
        limiter=None,
        tags={key: str(value) for key, value in tags.items()},
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
    "SafeContext",
    "category_value",
    "classify_exception",
    "is_reportable",
    "report_error",
]
