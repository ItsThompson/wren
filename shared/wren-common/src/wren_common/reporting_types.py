"""Runtime taxonomy and typing aliases for shared reporting."""

from __future__ import annotations

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
