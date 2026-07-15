"""MCP tool server bootstrap.

Builds the ``FastMCP`` instance the write tools (this ticket) and read tools
 register onto, and that:mod:`wren_mcp.app` mounts under the
bearer-guarded ``/mcp`` transport prefix. The server is a **thin dispatcher**:
tool execution, schema generation, and the Streamable HTTP protocol are the MCP
framework's job (spec section 07: validate tool shapes against MCP guidance,
``outputSchema`` + annotations); each tool body is one call to the backend
internal API via :class:`~wren_mcp.client.InternalApiClient`.

Streamable HTTP is stateless with JSON responses (the recommended production
mode): every tool call is a single authenticated POST, so there is no session to
pin per agent. DNS-rebinding protection is enabled in production and scoped to
the pinned resource host (defense-in-depth behind the tunnel + bearer boundary);
it is relaxed in development so the MCP Inspector (``just dev-mcp``) can attach
over localhost.
"""

from __future__ import annotations

from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from wren_mcp.settings import RsSettings

# Served at the mount root so the transport endpoint is exactly the guarded
# MCP_PATH (``/mcp``) rather than ``/mcp/mcp``.
_TRANSPORT_ROOT = "/"

_INSTRUCTIONS = (
    "Wren roadmap authoring and study tools. Author roadmaps as drafts: create, "
    "iteratively patch by slug ID, validate, then publish (one-way; published "
    "roadmaps are immutable except presentation metadata: fork to change "
    "structure). Retrieve the authoring guidance (SKILL.md, served at GET /skill) "
    "before authoring."
)


def _transport_security(settings: RsSettings) -> TransportSecuritySettings:
    """Scope DNS-rebinding protection to the pinned resource host in production;
    disable it in development for local Inspector use."""
    if settings.is_dev:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    host = urlparse(settings.resource).netloc
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[host],
        allowed_origins=[settings.resource],
    )


def create_mcp_server(settings: RsSettings) -> FastMCP:
    """Create the (tool-less) FastMCP server; callers register their tools."""
    return FastMCP(
        name=settings.service,
        instructions=_INSTRUCTIONS,
        stateless_http=True,
        json_response=True,
        streamable_http_path=_TRANSPORT_ROOT,
        transport_security=_transport_security(settings),
    )
