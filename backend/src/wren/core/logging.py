"""structlog configuration.

Configured once per process. In development, logs render as a human-readable
console stream; everywhere else they render as JSON.
The ``service`` field is bound per app via :func:`get_logger`, so external and
internal traffic is distinguishable without a process-global that would collide
when both apps run in one process (e.g. the smoke test).
"""

from __future__ import annotations

import logging
from typing import cast

import structlog

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

_configured = False


def _renderer(*, is_dev: bool) -> structlog.types.Processor:
    if is_dev:
        return structlog.dev.ConsoleRenderer()
    return structlog.processors.JSONRenderer()


def _build_processors(*, is_dev: bool) -> list[structlog.types.Processor]:
    """Ordered processor chain; the renderer is always last."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _renderer(is_dev=is_dev),
    ]


def configure_logging(*, environment: str, log_level: str) -> None:
    """Configure structlog once per process. Subsequent calls are no-ops.

    Both apps share one deployment environment and log level, so the first call
    wins and later calls (e.g. the second app in a two-app process) are ignored.
    """
    global _configured
    if _configured:
        return

    level = _LEVELS.get(log_level.lower(), logging.INFO)
    is_dev = environment.lower() == "development"

    structlog.configure(
        processors=_build_processors(is_dev=is_dev),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(service: str) -> structlog.stdlib.BoundLogger:
    """Return a logger with the ``service`` field bound onto every line."""
    return cast(
        "structlog.stdlib.BoundLogger",
        structlog.get_logger().bind(service=service),
    )
