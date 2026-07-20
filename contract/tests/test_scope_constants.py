"""Cross-package OAuth-scope-constant equality.

The backend Authorization Server (:8000) advertises its supported scopes in the
AS metadata document; the MCP resource server (:9000) advertises the same set in
its Protected Resource Metadata document. The two ship as separate images with no
shared code, so the scope set is a duplicated domain truth:
``wren.oauth.config`` declares it for the AS and ``wren_mcp.config`` re-declares
it for the RS. If the two diverge, a client discovers one scope set from the PRM
and a different set from the AS metadata, so a grant the RS advertises may be
rejected by the AS (or vice versa).

This assertion can only live in the dev/test-only ``contract`` project because it
is the sole interpreter where both ``wren.*`` and ``wren_mcp.*`` import together;
neither deployable depends on the other. ``mcp/tests/test_prm.py`` and
``backend/tests/test_oauth_keys_metadata.py`` each check their own document in
isolation, so neither can catch drift against the other package.
"""

from __future__ import annotations

from wren.oauth import config as backend_oauth_config
from wren_mcp import config as mcp_config


def test_supported_scopes_match_across_packages() -> None:
    assert mcp_config.SUPPORTED_SCOPES == backend_oauth_config.SUPPORTED_SCOPES


def test_roadmaps_read_scope_matches_across_packages() -> None:
    assert mcp_config.SCOPE_ROADMAPS_READ == backend_oauth_config.SCOPE_ROADMAPS_READ


def test_roadmaps_write_scope_matches_across_packages() -> None:
    assert mcp_config.SCOPE_ROADMAPS_WRITE == backend_oauth_config.SCOPE_ROADMAPS_WRITE


def test_progress_write_scope_matches_across_packages() -> None:
    assert mcp_config.SCOPE_PROGRESS_WRITE == backend_oauth_config.SCOPE_PROGRESS_WRITE
