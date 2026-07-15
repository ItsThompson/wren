"""Embedded OAuth 2.1 Authorization Server (spec section 08).

The backend external app embeds the AS (Metabase model); the MCP server is the
Resource Server (Ticket 20). This package owns Dynamic Client Registration, the
authorize/park flow, PKCE token exchange with rotating refresh, revocation, JWKS,
and AS metadata. Crypto (RS256 signing, JWKS, PKCE) is delegated to Authlib /
joserfc; this package never hand-rolls it.
"""
