"""Agent bearer-token verification.

Every MCP tool call carries an ``Authorization: Bearer`` access token minted by
the backend AS. This module verifies it end to end before any user identity is
trusted:

1. signature (RS256) against the AS public JWKS,
2. ``iss`` == the pinned AS issuer,
3. ``aud`` == this RS's MCP resource (audience binding: a token minted for a
   different resource is rejected, the confused-deputy defense), and
4. ``exp`` not passed.

Only then is ``sub`` taken as the single ``user_id`` the request is scoped to.
The token is **never** forwarded downstream; the internal client exchanges it for
an ``X-User-ID`` header (see :mod:`wren_mcp.client`). Crypto is delegated to
joserfc; this module owns only the claim contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from joserfc import jws, jwt
from joserfc.errors import JoseError
from joserfc.jwt import JWTClaimsRegistry

from wren_mcp.keys import KeyProvider

_ALGORITHMS = ["RS256"]


@dataclass(frozen=True)
class VerifiedAgentToken:
    """The resolved principal behind a valid bearer token."""

    user_id: str  # the token ``sub``; the single user every query is scoped to
    client_id: str
    scope: str


def _peek_kid(token: str) -> str | None:
    """Read the unverified ``kid`` from the JWS header, so the key provider can
    refetch on rotation before the (still-unverified) signature is checked."""
    try:
        signature = jws.extract_compact(token.encode("utf-8"))
    except (JoseError, ValueError):
        return None
    kid = signature.protected.get("kid")
    return kid if isinstance(kid, str) else None


class AgentTokenVerifier:
    """Verifies RS256 access tokens against the AS JWKS, audience-bound to this RS."""

    def __init__(self, key_provider: KeyProvider, *, issuer: str, resource: str) -> None:
        self._key_provider = key_provider
        self._issuer = issuer
        self._resource = resource

    async def verify(self, token: str) -> VerifiedAgentToken | None:
        """Return the resolved principal, or ``None`` if the token is not valid
        for this Resource Server (bad signature/issuer/audience/expiry or no sub)."""
        key_set = await self._key_provider.key_set_for(_peek_kid(token))
        try:
            decoded = jwt.decode(token, key_set, algorithms=_ALGORITHMS)
            self._claims_registry().validate(decoded.claims)
        except (JoseError, ValueError):
            return None
        subject = decoded.claims.get("sub")
        if not isinstance(subject, str) or not subject:
            return None
        return VerifiedAgentToken(
            user_id=subject,
            client_id=str(decoded.claims.get("client_id", "")),
            scope=str(decoded.claims.get("scope", "")),
        )

    def _claims_registry(self) -> JWTClaimsRegistry:
        # ``aud`` binding is the confused-deputy defense: a token whose audience is
        # not this RS's resource is rejected even if its signature is valid.
        return JWTClaimsRegistry(
            iss={"essential": True, "value": self._issuer},
            aud={"essential": True, "value": self._resource},
            exp={"essential": True},
        )
