"""Shared tool registrar for the MCP write + read surfaces.

Both :func:`wren_mcp.tools_write.register_write_tools` and
:func:`wren_mcp.tools_read.register_read_tools` register their tools through this
one registrar so every tool is wrapped identically: counted as
``mcp_tool_invocations_total{tool,outcome}`` (:mod:`wren_mcp.tool_metrics`) before
being handed to FastMCP. The counting wrapper preserves the tool's
name/signature/return annotation (``functools.wraps``), so FastMCP's schema
generation (which follows ``__wrapped__``) produces an unchanged contract and the
frozen schema snapshot is unaffected.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from wren_mcp.tool_metrics import count_invocations

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations


def counted_tool_registrar[ToolFn: Callable[..., Awaitable[Any]]](
    mcp: FastMCP,
) -> Callable[[ToolAnnotations], Callable[[ToolFn], ToolFn]]:
    """Return a ``tool(annotations)`` decorator that counts then registers onto ``mcp``."""

    def tool(annotations: ToolAnnotations) -> Callable[[ToolFn], ToolFn]:
        def register(fn: ToolFn) -> ToolFn:
            mcp.tool(annotations=annotations)(count_invocations(fn))
            return fn

        return register

    return tool
