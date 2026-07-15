"""Shared tool registrar for the MCP write + read surfaces (spec sections 07/11).

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
from typing import Any, TypeVar

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from wren_mcp.tool_metrics import count_invocations

# A tool coroutine; the registrar preserves this exact type so call sites keep
# their real signatures (and thus their generated schemas).
_ToolFn = TypeVar("_ToolFn", bound=Callable[..., Awaitable[Any]])


def counted_tool_registrar(
    mcp: FastMCP,
) -> Callable[[ToolAnnotations], Callable[[_ToolFn], _ToolFn]]:
    """Return a ``tool(annotations)`` decorator that counts then registers onto ``mcp``."""

    def tool(annotations: ToolAnnotations) -> Callable[[_ToolFn], _ToolFn]:
        def register(fn: _ToolFn) -> _ToolFn:
            mcp.tool(annotations=annotations)(count_invocations(fn))
            return fn

        return register

    return tool
