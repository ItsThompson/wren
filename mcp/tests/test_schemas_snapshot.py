"""Frozen MCP tool-schema snapshot (spec section 13 contract-freeze).

The write-tool contracts are deliberately frozen (spec section 07). This is the
MCP analog of the OpenAPI drift check: it serializes each registered tool's
machine contract (name + annotations + input/output JSON Schema) and compares it
against a committed snapshot, so any accidental shape change fails the build
until the snapshot is updated on purpose. Tool descriptions (prose) are excluded
so wording can improve without a snapshot churn.

Regenerate deliberately with ``WREN_UPDATE_SNAPSHOTS=1 uv run pytest -k snapshot``
after an intended contract change, then review the diff.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from wren_mcp.client import InternalApiClient
from wren_mcp.mcp_server import create_mcp_server
from wren_mcp.settings import SERVICE, RsSettings
from wren_mcp.tools_write import register_write_tools

_SNAPSHOT = Path(__file__).parent / "snapshots" / "write_tools_schema.json"


def _settings() -> RsSettings:
    return RsSettings(
        service=SERVICE,
        environment="production",
        log_level="critical",
        host="127.0.0.1",
        port=9000,
        issuer="https://api.usewren.com",
        resource="https://mcp.usewren.com",
        backend_internal_url="http://backend:8001",
        internal_api_token="tok",
    )


def _build_server() -> FastMCP:
    http = httpx.AsyncClient(base_url="http://backend:8001")
    mcp = create_mcp_server(_settings())
    register_write_tools(mcp, InternalApiClient(http, api_token="tok"))
    return mcp


async def _contract() -> list[dict[str, Any]]:
    mcp = _build_server()
    tools = await mcp.list_tools()
    return [
        {
            "name": tool.name,
            "annotations": tool.annotations.model_dump() if tool.annotations else None,
            "inputSchema": tool.inputSchema,
            "outputSchema": tool.outputSchema,
        }
        for tool in sorted(tools, key=lambda tool: tool.name)
    ]


async def test_write_tool_schemas_match_the_frozen_snapshot() -> None:
    contract = await _contract()
    serialized = json.dumps(contract, indent=2, sort_keys=True)

    if os.environ.get("WREN_UPDATE_SNAPSHOTS"):
        _SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        _SNAPSHOT.write_text(serialized + "\n")

    assert _SNAPSHOT.exists(), "snapshot missing; regenerate with WREN_UPDATE_SNAPSHOTS=1"
    expected = _SNAPSHOT.read_text().strip()
    assert serialized == expected, (
        "MCP write-tool contract drifted. If intentional, regenerate with "
        "WREN_UPDATE_SNAPSHOTS=1 and review the diff."
    )
