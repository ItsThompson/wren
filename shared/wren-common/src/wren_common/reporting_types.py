"""Runtime taxonomy and typing aliases for shared reporting."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from enum import StrEnum
from typing import cast


class ReportCategory(StrEnum):
    EXPECTED = "expected"
    UNEXPECTED = "unexpected"


class Kind(StrEnum):
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    PERMISSION = "permission"
    UPSTREAM = "upstream"
    TIMEOUT = "timeout"
    DATABASE = "database"
    INTERNAL = "internal"


class Domain(StrEnum):
    ROADMAPS = "roadmaps"
    PROGRESS = "progress"
    ACCOUNTS = "accounts"
    OAUTH = "oauth"
    SKILL = "skill"
    DB = "db"
    MCP = "mcp"


class LogEvent(StrEnum):
    UNHANDLED_EXCEPTION = "unhandled_exception"
    SENTRY_DISABLED = "sentry_disabled"
    SENTRY_INITIALIZED = "sentry_initialized"


class ReportLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


type Operation = str
type GroupKey = str
type BoundedTags = Mapping[str, str]
type SafeContextValue = str | bool | int | float | None
type SafeContext = Mapping[str, SafeContextValue]

# These fields are controlled by the reporter and cannot be supplied by callers.
RESERVED_TAG_KEYS = frozenset(
    {"operation", "domain", "kind", "log_event", "level", "report_category", "error_kind"}
)
REGISTERED_TAG_KEYS = frozenset(
    {
        "code",
        "component",
        "expected",
        "method",
        "reason",
        "required_scope",
        "service",
        "status",
        "tool",
    }
)
# Keep the old name available to callers while making the registry explicit.
OPTIONAL_TAG_KEYS = REGISTERED_TAG_KEYS
SAFE_CONTEXT_KEYS = frozenset({"method", "operation", "path", "status", "template"})
CONTEXT_TRUNCATED_KEY = "truncated"
CONTEXT_ORIGINAL_BYTES_KEY = "original_bytes"
MAX_TAG_KEY_LENGTH = 32
MAX_TAG_VALUE_LENGTH = 200
MAX_CONTEXT_BYTES = 8 * 1024


def sanitize_tags(value: BoundedTags | None) -> dict[str, str]:
    """Keep only registered, bounded, caller-controlled tag fields."""
    if not value:
        return {}
    result: dict[str, str] = {}
    for key, item in value.items():
        if (
            type(key) is not str
            or key in RESERVED_TAG_KEYS
            or key not in REGISTERED_TAG_KEYS
            or len(key) > MAX_TAG_KEY_LENGTH
            or type(item) is not str
            or len(item.encode("utf-8")) > MAX_TAG_VALUE_LENGTH
        ):
            continue
        result[key] = item
    return result


def _context_size(value: Mapping[str, object]) -> int:
    return len(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))


def _safe_context_value(value: object) -> SafeContextValue | None:
    if value is None or type(value) is str or type(value) is bool or type(value) is int:
        return cast("SafeContextValue", value)
    if type(value) is float and math.isfinite(value):
        return value
    return None


def _truncated_context(
    result: dict[str, SafeContextValue],
    *,
    key: str,
    value: str,
    original_bytes: int,
) -> dict[str, SafeContextValue] | None:
    metadata = {
        CONTEXT_TRUNCATED_KEY: True,
        CONTEXT_ORIGINAL_BYTES_KEY: original_bytes,
    }
    base_result = {
        key: item
        for key, item in result.items()
        if key not in {CONTEXT_TRUNCATED_KEY, CONTEXT_ORIGINAL_BYTES_KEY}
    }
    low, high = 0, len(value)
    while low < high:
        midpoint = (low + high + 1) // 2
        trial = {**base_result, key: value[:midpoint], **metadata}
        if _context_size(trial) <= MAX_CONTEXT_BYTES:
            low = midpoint
        else:
            high = midpoint - 1
    trial = {**base_result, key: value[:low], **metadata}
    if _context_size(trial) > MAX_CONTEXT_BYTES:
        return None
    return trial


def sanitize_context(value: SafeContext | None) -> dict[str, SafeContextValue]:
    """Keep typed, allowlisted context within the Sentry payload budget."""
    if not value:
        return {}

    safe_items: list[tuple[str, SafeContextValue]] = []
    for key, raw_item in value.items():
        if type(key) is not str or key not in SAFE_CONTEXT_KEYS:
            continue
        item = _safe_context_value(raw_item)
        if item is None and raw_item is not None:
            continue
        safe_items.append((key, item))

    result: dict[str, SafeContextValue] = {}
    for key, item in safe_items:
        if type(item) is str:
            continue
        trial = {**result, key: item}
        if _context_size(trial) <= MAX_CONTEXT_BYTES:
            result[key] = item

    truncated_bytes = 0
    for key, item in safe_items:
        if type(item) is not str:
            continue
        trial = {**result, key: item}
        if _context_size(trial) <= MAX_CONTEXT_BYTES:
            result[key] = item
            continue

        original_bytes = len(item.encode("utf-8"))
        truncated_bytes += original_bytes
        truncated = _truncated_context(
            result,
            key=key,
            value=item,
            original_bytes=truncated_bytes,
        )
        if truncated is None:
            continue
        result = truncated

    if truncated_bytes:
        result[CONTEXT_TRUNCATED_KEY] = True
        result[CONTEXT_ORIGINAL_BYTES_KEY] = truncated_bytes
    return result
