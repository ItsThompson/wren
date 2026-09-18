"""MCP tool-invocation domain counter.

Counts every agent tool call as ``mcp_tool_invocations_total{tool,outcome}`` so
the operator can see authoring/study activity and per-tool error rates. Kept on a
dedicated registry that :func:`wren_common.metrics.instrument` exposes on
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

import structlog
from prometheus_client import CollectorRegistry, Counter

from wren_common.logging import get_logger
from wren_common.reporting import is_reportable
from wren_mcp.reporting import report_mcp_error
from wren_mcp.settings import SERVICE
from wren_mcp.tool_errors import (
    BackendToolError,
    BackendUnavailableToolError,
    ExpectedToolError,
)

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
    """Wrap a registered MCP tool coroutine to count its invocations and outcome.

    Registration supplies the exposed tool name. Rejecting unregistered functions
    before creating the wrapper prevents arbitrary function names from reaching
    logs, metrics, tags, or reporting operations.
    """
    from wren_mcp.tool_registry import registered_tool_name

    tool_name = registered_tool_name(fn)
    if tool_name is None:
        raise ValueError("count_invocations requires a function registered as an MCP tool")

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        _log.info("tool_invoked", tool=tool_name)
        try:
            result = await fn(*args, **kwargs)
        except Exception as exc:
            TOOL_INVOCATIONS.labels(tool=tool_name, outcome="error").inc()
            # Backend HTTP status/code are available only for backend-hop failures;
            # other exceptions log the tool + error_type with no backend fields.
            backend = exc if isinstance(exc, BackendToolError) else None
            should_report = isinstance(exc, BackendUnavailableToolError) or (
                not isinstance(exc, ExpectedToolError) and is_reportable(exc)
            )
            if should_report:
                user_id = structlog.contextvars.get_contextvars().get("user_id")
                report_mcp_error(
                    exc,
                    operation_name=f"tool.{tool_name}",
                    kind_name=(
                        exc.kind if isinstance(exc, BackendUnavailableToolError) else "internal"
                    ),
                    log_event_name="unhandled_exception",
                    level_name=(
                        "warning" if isinstance(exc, BackendUnavailableToolError) else "error"
                    ),
                    user_id=user_id if isinstance(user_id, str) else None,
                    bounded_tags={"tool": tool_name},
                    context_data={"status": getattr(exc, "status", None)},
                    group_key=tool_name,
                )
            _log.warning(
                "tool_failed",
                tool=tool_name,
                error_type=type(exc).__name__,
                status=backend.status_code if backend is not None else None,
                code=backend.code if backend is not None else None,
            )
            raise
        TOOL_INVOCATIONS.labels(tool=tool_name, outcome="ok").inc()
        return result

    return wrapper  # type: ignore[return-value]
