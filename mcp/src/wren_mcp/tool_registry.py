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

_REGISTERED_TOOL_NAMES: set[str] = set()
_REGISTERED_TOOLS: dict[Callable[..., Any], str] = {}


def is_registered_tool(tool_name: object) -> bool:
    """Return whether FastMCP registered a tool with this exact name."""
    return type(tool_name) is str and tool_name in _REGISTERED_TOOL_NAMES


def registered_tool_names() -> frozenset[str]:
    """Return the names registered through :func:`counted_tool_registrar`."""
    return frozenset(_REGISTERED_TOOL_NAMES)


def registered_tool_name(tool: object) -> str | None:
    """Return the validated exposed name for a registered function."""
    if not callable(tool):
        return None
    try:
        return _REGISTERED_TOOLS.get(tool)
    except TypeError:
        return None


if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations


def counted_tool_registrar[ToolFn: Callable[..., Awaitable[Any]]](
    mcp: FastMCP,
) -> Callable[[ToolAnnotations], Callable[[ToolFn], ToolFn]]:
    """Return a ``tool(annotations)`` decorator that counts then registers onto ``mcp``."""

    def tool(annotations: ToolAnnotations) -> Callable[[ToolFn], ToolFn]:
        def register(fn: ToolFn) -> ToolFn:
            tool_name = fn.__name__
            _REGISTERED_TOOLS[fn] = tool_name
            _REGISTERED_TOOL_NAMES.add(tool_name)
            mcp.tool(annotations=annotations)(count_invocations(fn))
            return fn

        return register

    return tool
