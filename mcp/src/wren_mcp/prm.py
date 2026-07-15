"""Protected Resource Metadata (RFC 9728), served by this Resource Server.

The MCP server owns the PRM; the
backend AS owns the AS metadata. The PRM advertises which Authorization Server
protects this resource, so a client that hits a 401 can discover the AS and run
the OAuth handshake. Every URL is built from **pinned** config (the ``resource``
is this RS's public URL, the ``authorization_servers`` entry is the pinned AS
issuer), never a request host: the Site-URL gotcha applies to the RS as well.

The 401 challenge's ``WWW-Authenticate`` header points at this document
(:func:`www_authenticate_challenge`), completing the RFC 9728 discovery chain.
"""

from __future__ import annotations

from typing import Any

from wren_mcp.config import (
    BEARER_METHOD_HEADER,
    PRM_PATH,
    SUPPORTED_SCOPES,
)


def prm_resource_metadata_url(resource: str) -> str:
    """Absolute URL of this RS's PRM document, built from the pinned resource."""
    return f"{resource.rstrip('/')}{PRM_PATH}"


def build_prm_document(*, resource: str, issuer: str) -> dict[str, Any]:
    """The RFC 9728 Protected Resource Metadata document for this RS.

    ``resource`` is this RS's pinned public URL (agent tokens are audience-bound
    to it); ``authorization_servers`` names the backend AS a client discovers the
    OAuth endpoints from.
    """
    return {
        "resource": resource,
        "authorization_servers": [issuer],
        "scopes_supported": list(SUPPORTED_SCOPES),
        "bearer_methods_supported": [BEARER_METHOD_HEADER],
    }


def www_authenticate_challenge(resource: str) -> str:
    """The ``WWW-Authenticate`` header value for a 401 (RFC 9728 section 5.1).

    Points the client at this RS's PRM document so it can discover the AS and
    authenticate, rather than failing opaquely.
    """
    return f'Bearer resource_metadata="{prm_resource_metadata_url(resource)}"'
