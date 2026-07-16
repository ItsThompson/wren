"""MCP tool-invocation domain counter.

Counts every agent tool call as ``mcp_tool_invocations_total{tool,outcome}`` so
the operator can see authoring/study activity and per-tool error rates. Kept on a
dedicated registry that :func:`wren_mcp.metrics.instrument` exposes on
``/metrics`` alongside the private HTTP registry, mirroring the backend split
(names/labels follow a stable convention so rules/dashboards drop in later).

The counting wrapper preserves the wrapped function's name, signature, and return
annotation via :func:`functools.wraps`, so FastMCP's schema generation (which
follows ``__wrapped__``) produces an identical tool contract: the frozen
tool-schema snapshot is unaffected.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any

from prometheus_client import CollectorRegistry, Counter

from wren_mcp.logging import get_logger
from wren_mcp.settings import SERVICE

_log = get_logger(SERVICE)

# Dedicated registry for MCP domain metrics, exposed alongside the private HTTP
# registry so a single process can serve both without duplicate-timeseries errors.
TOOL_METRICS_REGISTRY = CollectorRegistry()

TOOL_INVOCATIONS = Counter(
    "mcp_tool_invocations_total",
    "MCP tool calls by tool name and outcome (ok/error).",
    labelnames=("tool", "outcome"),
    registry=TOOL_METRICS_REGISTRY,
)


def count_invocations[F: Callable[..., Awaitable[Any]]](fn: F) -> F:
    """Wrap an MCP tool coroutine to count its invocations and outcome.

    The tool name is the wrapped function's ``__name__`` (the name FastMCP also
    registers it under), so the label always matches the exposed tool. Each call
    logs ``tool_invoked`` on entry and ``tool_failed`` on error (carrying the
    backend HTTP status/code when the failure came from the backend hop);
    ``user_id``/``request_id`` ride along via contextvars and no raw token is
    ever logged.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        _log.info("tool_invoked", tool=fn.__name__)
        try:
            result = await fn(*args, **kwargs)
        except Exception as exc:
            TOOL_INVOCATIONS.labels(tool=fn.__name__, outcome="error").inc()
            _log.warning(
                "tool_failed",
                tool=fn.__name__,
                error_type=type(exc).__name__,
                status=getattr(exc, "status_code", None),
                code=getattr(exc, "code", None),
            )
            raise
        TOOL_INVOCATIONS.labels(tool=fn.__name__, outcome="ok").inc()
        return result

    return wrapper  # type: ignore[return-value]
