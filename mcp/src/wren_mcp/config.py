"""MCP Resource Server constants.

These are the wire-contract constants the RS shares with the backend: the
well-known discovery paths, the OAuth scopes, and the internal-boundary header
names. The header names in particular MUST match the backend's
``wren.core.identity`` (``USER_ID_HEADER`` / ``INTERNAL_TOKEN_HEADER``): the RS
and the backend are separate images with no shared code, so this is a duplicated
domain truth kept in sync by contract (asserted in the client tests).
"""

from __future__ import annotations

# Protected Resource Metadata (RFC 9728), served by this RS. The 401 challenge's
# WWW-Authenticate header points clients here for AS discovery.
PRM_PATH = "/.well-known/oauth-protected-resource"

# Authorization Server Metadata (RFC 8414), served by the backend AS. The RS
# reads it (built off the pinned issuer) to discover the JWKS URI.
AS_METADATA_PATH = "/.well-known/oauth-authorization-server"

# The MCP transport mount point. Unauthenticated calls here get 401 +
# WWW-Authenticate; the tool dispatch that sits behind the bearer guard is
# Tickets 21/22.
MCP_PATH = "/mcp"

# OAuth scopes advertised in the PRM. Mirrors the backend AS's
# supported scopes so a client sees a consistent set on both documents.
SCOPE_ROADMAPS_READ = "roadmaps:read"
SCOPE_ROADMAPS_WRITE = "roadmaps:write"
SCOPE_PROGRESS_WRITE = "progress:write"
SUPPORTED_SCOPES: tuple[str, ...] = (
    SCOPE_ROADMAPS_READ,
    SCOPE_ROADMAPS_WRITE,
    SCOPE_PROGRESS_WRITE,
)

# Bearer methods advertised in the PRM: agents pass the token in the
# Authorization header only, never in the URL (RFC 9728 / spec section 08).
BEARER_METHOD_HEADER = "header"

# Internal-boundary headers the RS sends downstream to the backend internal app.
# MUST match wren.core.identity in the backend (separate image, shared contract):
# the internal app trusts X-User-ID only behind a valid INTERNAL_API_TOKEN.
USER_ID_HEADER = "X-User-ID"
INTERNAL_TOKEN_HEADER = "X-Internal-Api-Token"
