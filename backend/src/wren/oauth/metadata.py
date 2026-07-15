"""Authorization Server Metadata (RFC 8414), built purely from pinned config.

The document advertises the AS's endpoints and capabilities to clients. Every URL
in it is derived from :class:`OAuthConfig` (the pinned issuer), never the request
host: the Site-URL gotcha (spec section 08) means a request-derived issuer would
be rejected by clients that opened the flow at ``api.usewren.com``. ``S256`` is
advertised as the only PKCE method, matching the enforcement in the flow.
"""

from __future__ import annotations

from typing import Any

from wren.oauth.config import (
    AUTHORIZE_PATH,
    CODE_CHALLENGE_METHOD_S256,
    GRANT_TYPE_AUTHORIZATION_CODE,
    GRANT_TYPE_REFRESH_TOKEN,
    JWKS_PATH,
    REGISTER_PATH,
    RESPONSE_TYPE_CODE,
    REVOKE_PATH,
    SUPPORTED_SCOPES,
    TOKEN_ENDPOINT_AUTH_NONE,
    TOKEN_PATH,
    OAuthConfig,
)


def build_as_metadata(config: OAuthConfig) -> dict[str, Any]:
    """The RFC 8414 Authorization Server Metadata document for this AS."""
    return {
        "issuer": config.issuer,
        "authorization_endpoint": config.endpoint(AUTHORIZE_PATH),
        "token_endpoint": config.endpoint(TOKEN_PATH),
        "registration_endpoint": config.endpoint(REGISTER_PATH),
        "revocation_endpoint": config.endpoint(REVOKE_PATH),
        "jwks_uri": config.endpoint(JWKS_PATH),
        "scopes_supported": list(SUPPORTED_SCOPES),
        "response_types_supported": [RESPONSE_TYPE_CODE],
        "response_modes_supported": ["query"],
        "grant_types_supported": [GRANT_TYPE_AUTHORIZATION_CODE, GRANT_TYPE_REFRESH_TOKEN],
        "code_challenge_methods_supported": [CODE_CHALLENGE_METHOD_S256],
        "token_endpoint_auth_methods_supported": [TOKEN_ENDPOINT_AUTH_NONE],
    }
