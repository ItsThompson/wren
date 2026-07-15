"""MCP server bootstrap: transport-security policy (spec sections 07/08/11).

DNS-rebinding protection is scoped to the pinned resource host in production
(defense-in-depth behind the tunnel + bearer boundary) and relaxed in
development so the MCP Inspector can attach over localhost.
"""

from __future__ import annotations

from wren_mcp.mcp_server import create_mcp_server
from wren_mcp.settings import SERVICE, RsSettings


def _settings(environment: str) -> RsSettings:
    return RsSettings(
        service=SERVICE,
        environment=environment,
        log_level="critical",
        host="127.0.0.1",
        port=9000,
        issuer="https://api.usewren.com",
        resource="https://mcp.usewren.com",
        backend_internal_url="http://backend:8001",
        internal_api_token="tok",
    )


def test_production_scopes_protection_to_the_pinned_resource_host() -> None:
    security = create_mcp_server(_settings("production")).settings.transport_security
    assert security is not None
    assert security.enable_dns_rebinding_protection is True
    assert security.allowed_hosts == ["mcp.usewren.com"]
    assert security.allowed_origins == ["https://mcp.usewren.com"]


def test_development_relaxes_protection_for_the_inspector() -> None:
    security = create_mcp_server(_settings("development")).settings.transport_security
    assert security is not None
    assert security.enable_dns_rebinding_protection is False


def test_create_mcp_server_is_stateless_json_and_mounts_at_root() -> None:
    mcp = create_mcp_server(_settings("production"))
    assert mcp.settings.stateless_http is True
    assert mcp.settings.json_response is True
    # Served at the mount root so the endpoint is exactly the guarded MCP_PATH.
    assert mcp.settings.streamable_http_path == "/"
