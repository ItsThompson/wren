"""Frozen MCP tool-schema snapshot (contract-freeze).

The write- and read-tool contracts are deliberately frozen.
This is the MCP analog of the OpenAPI drift check: it serializes each registered
tool's machine contract (name + annotations + input/output JSON Schema) and
compares it against a committed snapshot, so any accidental shape change fails the
build until the snapshot is updated on purpose. Tool descriptions (prose) are
excluded so wording can improve without a snapshot churn.

Regenerate deliberately with ``WREN_UPDATE_SNAPSHOTS=1 uv run pytest -k snapshot``
after an intended contract change, then review the diff.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import SecretStr

from wren_mcp.client import InternalApiClient
from wren_mcp.mcp_server import create_mcp_server
from wren_mcp.settings import SERVICE, RsSettings
from wren_mcp.tools_read import register_read_tools
from wren_mcp.tools_write import register_write_tools

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

_SNAPSHOT = Path(__file__).parent / "snapshots" / "tools_schema.json"


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
        internal_api_token=SecretStr("tok"),
    )


def _build_server() -> FastMCP:
    http = httpx.AsyncClient(base_url="http://backend:8001")
    client = InternalApiClient(http, api_token=SecretStr("tok"))
    mcp = create_mcp_server(_settings())
    register_write_tools(mcp, client)
    register_read_tools(mcp, client)
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


async def test_tool_schemas_match_the_frozen_snapshot() -> None:
    contract = await _contract()
    serialized = json.dumps(contract, indent=2, sort_keys=True)

    if os.environ.get("WREN_UPDATE_SNAPSHOTS"):
        _SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        _SNAPSHOT.write_text(serialized + "\n")

    assert _SNAPSHOT.exists(), "snapshot missing; regenerate with WREN_UPDATE_SNAPSHOTS=1"
    expected = _SNAPSHOT.read_text().strip()
    assert serialized == expected, (
        "MCP tool contract drifted. If intentional, regenerate with "
        "WREN_UPDATE_SNAPSHOTS=1 and review the diff."
    )


# --------------------------------------------------------------------------- #
# Structural guard: classify drift as cosmetic vs contract-breaking            #
# --------------------------------------------------------------------------- #
#
# The Group-A tool schemas are generated from the backend OpenAPI, so a backend
# edit changes generated ``title``/``description`` values (cosmetic) and can add a
# non-structural ``default: []`` or reorder a ``required`` array. Those are safe to
# accept in a snapshot refresh. A change to a field NAME, TYPE, enum value,
# ``required`` membership, or a discriminator is an agent-facing contract change
# and must be scrutinized. This guard normalizes both sides to the structural
# contract only, so it stays green through a cosmetic refresh but fails on a real
# field/type/enum/required/discriminator change: when the exact snapshot test
# above fails, run this to tell the two apart before refreshing.

_COSMETIC_KEYS = frozenset({"title", "description"})
_NAME_MAPS = frozenset({"properties", "$defs", "patternProperties", "definitions"})
_NON_STRUCTURAL_DEFAULTS: tuple[object, ...] = ([], None, {})


def _structural(node: Any) -> Any:
    """Reduce a tool schema to its structural contract.

    Drops the cosmetic ``title``/``description`` schema keywords (never the field
    NAMES under ``properties``/``$defs``), sorts each ``required`` array (order is
    not part of the contract), and drops a non-structural empty ``default``
    (``[]``/``null``/``{}``) so a generated ``default: []`` reads the same as a
    hand-authored ``default_factory`` that omits the key.
    """
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in _COSMETIC_KEYS:
                continue
            if key in _NAME_MAPS and isinstance(value, dict):
                out[key] = {name: _structural(sub) for name, sub in value.items()}
            elif key == "required" and isinstance(value, list):
                out[key] = sorted(value)
            elif key == "default" and value in _NON_STRUCTURAL_DEFAULTS:
                continue
            else:
                out[key] = _structural(value)
        return out
    if isinstance(node, list):
        return [_structural(item) for item in node]
    return node


async def test_tool_schemas_are_structurally_unchanged() -> None:
    """The live tool contract matches the snapshot on every structural field.

    Unlike the exact snapshot test, this tolerates cosmetic ``title``/
    ``description`` edits, an added empty ``default``, and ``required`` reordering.
    A failure here means a real field/type/enum/required/discriminator change
    reached an agent-facing tool: do not accept it as a routine snapshot refresh.
    """
    assert _SNAPSHOT.exists(), "snapshot missing; regenerate with WREN_UPDATE_SNAPSHOTS=1"
    live = _structural(await _contract())
    committed = _structural(json.loads(_SNAPSHOT.read_text()))
    assert live == committed, (
        "MCP tool contract changed a structural field (name, type, enum, required "
        "membership, or discriminator). This is an agent-facing contract change, "
        "not a cosmetic refresh: investigate before updating the snapshot."
    )
