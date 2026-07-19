"""Cross-package internal-boundary header-constant equality.

The backend internal app (:8001) and the MCP resource server ship as separate
images with no shared code, so the internal-boundary header names are a
duplicated domain truth: ``wren.core.identity`` declares them for the backend and
``wren_mcp.config`` re-declares them for the RS. If the two diverge, the RS sends
headers the backend does not read, silently breaking the trusted internal hop.

The request-correlation header is the same kind of duplicated truth: the MCP
client sends ``X-Request-ID`` (``wren_mcp.client.REQUEST_ID_HEADER``) and the
backend correlation middleware honors it
(``wren.core.correlation.REQUEST_ID_HEADER``); a divergence would silently break
the MCP->backend correlation hop.

This assertion can only live in the dev/test-only ``contract`` project because it
is the sole interpreter where both ``wren.*`` and ``wren_mcp.*`` import together;
neither deployable depends on the other. ``mcp/tests/test_client.py`` compares the
MCP constant only to itself, so it cannot catch drift against the backend.
"""

from __future__ import annotations

from wren.core import correlation as backend_correlation
from wren.core import identity as backend_identity
from wren_mcp import client as mcp_client
from wren_mcp import config as mcp_config


def test_user_id_header_matches_across_packages() -> None:
    assert mcp_config.USER_ID_HEADER == backend_identity.USER_ID_HEADER


def test_internal_token_header_matches_across_packages() -> None:
    assert mcp_config.INTERNAL_TOKEN_HEADER == backend_identity.INTERNAL_TOKEN_HEADER


def test_request_id_header_matches_across_packages() -> None:
    # The MCP client sends X-Request-ID; the backend correlation middleware honors
    # that exact header. Drift would silently break the MCP->backend hop.
    assert mcp_client.REQUEST_ID_HEADER == backend_correlation.REQUEST_ID_HEADER
