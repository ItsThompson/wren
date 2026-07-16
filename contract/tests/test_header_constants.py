"""Cross-package internal-boundary header-constant equality (F18c, F17).

The backend internal app (:8001) and the MCP resource server ship as separate
images with no shared code, so the internal-boundary header names are a
duplicated domain truth: ``wren.core.identity`` declares them for the backend and
``wren_mcp.config`` re-declares them for the RS. If the two diverge, the RS sends
headers the backend does not read, silently breaking the trusted internal hop.

This assertion can only live in the dev/test-only ``contract`` project because it
is the sole interpreter where both ``wren.*`` and ``wren_mcp.*`` import together;
neither deployable depends on the other. ``mcp/tests/test_client.py`` compares the
MCP constant only to itself, so it cannot catch drift against the backend.
"""

from __future__ import annotations

from wren.core import identity as backend_identity
from wren_mcp import config as mcp_config


def test_user_id_header_matches_across_packages() -> None:
    assert mcp_config.USER_ID_HEADER == backend_identity.USER_ID_HEADER


def test_internal_token_header_matches_across_packages() -> None:
    assert mcp_config.INTERNAL_TOKEN_HEADER == backend_identity.INTERNAL_TOKEN_HEADER
