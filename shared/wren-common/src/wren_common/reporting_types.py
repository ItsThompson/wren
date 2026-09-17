"""Runtime taxonomy and typing aliases for shared reporting."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from enum import StrEnum


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
type SafeContext = Mapping[str, object]

# These fields are controlled by the reporter and cannot be supplied by callers.
RESERVED_TAG_KEYS = frozenset(
    {"operation", "domain", "kind", "log_event", "level", "report_category", "error_kind"}
)
OPTIONAL_TAG_KEYS = frozenset(
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
SAFE_CONTEXT_KEYS = frozenset({"method", "operation", "path", "status", "template"})
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
            not isinstance(key, str)
            or key in RESERVED_TAG_KEYS
            or key not in OPTIONAL_TAG_KEYS
            or len(key) > MAX_TAG_KEY_LENGTH
            or not isinstance(item, str)
        ):
            continue
        result[key] = item[:MAX_TAG_VALUE_LENGTH]
    return result


def _context_size(value: Mapping[str, object]) -> int:
    return len(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode())


def sanitize_context(value: SafeContext | None) -> dict[str, object]:
    """Keep safe scalar context fields within the Sentry payload budget."""
    if not value:
        return {}

    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or key not in SAFE_CONTEXT_KEYS:
            continue
        if isinstance(item, str):
            candidate: object = item
        elif isinstance(item, (bool, int)) or (isinstance(item, float) and math.isfinite(item)):
            candidate = item
        elif item is None:
            candidate = None
        else:
            continue

        if isinstance(candidate, str):
            low, high = 0, len(candidate)
            while low < high:
                midpoint = (low + high + 1) // 2
                trial = {**result, key: candidate[:midpoint]}
                if _context_size(trial) <= MAX_CONTEXT_BYTES:
                    low = midpoint
                else:
                    high = midpoint - 1
            candidate = candidate[:low]

        trial = {**result, key: candidate}
        if _context_size(trial) <= MAX_CONTEXT_BYTES:
            result[key] = candidate
    return result
