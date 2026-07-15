"""MCP tool-invocation domain counter (spec section 11).

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
    registers it under), so the label always matches the exposed tool.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            result = await fn(*args, **kwargs)
        except Exception:
            TOOL_INVOCATIONS.labels(tool=fn.__name__, outcome="error").inc()
            raise
        TOOL_INVOCATIONS.labels(tool=fn.__name__, outcome="ok").inc()
        return result

    return wrapper  # type: ignore[return-value]
