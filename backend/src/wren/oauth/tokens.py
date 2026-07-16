"""Agent tokens: RS256 access tokens and opaque rotating refresh tokens.

Access tokens are asymmetrically signed (RS256) and **audience-bound** to the MCP
resource, so the Resource Server verifies them via the AS JWKS
and rejects any token whose ``aud`` is not the MCP resource. Refresh tokens are
high-entropy opaque strings stored only as a SHA-256 hash (secrets hashed at
rest); rotation is enforced by the service, which revokes the
presented refresh and mints a fresh one on every exchange.

Signing/verification is delegated to joserfc; this module owns only the claim
shape and the token lifetimes.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwt import JWTClaimsRegistry

from wren.oauth.config import OAuthConfig
from wren.oauth.injection import Clock, OpaqueIdFactory, new_hex_id, utcnow
from wren.oauth.keys import SigningKeySet

_ALGORITHMS = ["RS256"]
# Opaque refresh-token entropy (bytes -> ~43 char urlsafe string).
_REFRESH_TOKEN_BYTES = 32


@dataclass(frozen=True)
class MintedAccessToken:
    """A freshly signed access token plus the seconds until it expires."""

    token: str
    expires_in: int
    jti: str


@dataclass(frozen=True)
class VerifiedAccessToken:
    """Verified access-token claims: the user, client, audience, and scope."""

    subject: str
    client_id: str
    scope: str
    audience: str
    jti: str


class AccessTokenCodec:
    """Mints and verifies RS256 access tokens for one signing key set and config."""

    def __init__(
        self,
        keyset: SigningKeySet,
        config: OAuthConfig,
        *,
        clock: Clock = utcnow,
        new_id: OpaqueIdFactory = new_hex_id,
    ) -> None:
        self._keyset = keyset
        self._config = config
        # Injected so mint and verify share one clock (tests advance it to assert
        # expiry) and the jti is deterministic; defaults reproduce the ambient calls.
        self._clock = clock
        self._new_id = new_id

    def mint(self, *, subject: str, client_id: str, scope: str, audience: str) -> MintedAccessToken:
        """Sign a short-lived access token bound to ``audience`` (the MCP resource)."""
        now = self._clock()
        expires_in = int(self._config.access_ttl.total_seconds())
        jti = self._new_id()
        claims = {
            "iss": self._config.issuer,
            "sub": subject,
            "aud": audience,
            "client_id": client_id,
            "scope": scope,
            "iat": int(now.timestamp()),
            "exp": int(now.timestamp()) + expires_in,
            "jti": jti,
        }
        token = jwt.encode(self._keyset.signing_header(), claims, self._keyset.active)
        return MintedAccessToken(token=token, expires_in=expires_in, jti=jti)

    def verify(self, token: str) -> VerifiedAccessToken | None:
        """Verify signature (via JWKS), issuer, audience, and expiry; ``None`` on failure.

        The Resource Server owns request-time bearer validation; this
        mirror is used to prove audience binding and expiry in the AS's own tests.
        Expiry is checked against the injected clock so a pinned clock governs the
        mint -> expire assertion.
        """
        try:
            decoded = jwt.decode(token, self._keyset.verifying_key_set(), algorithms=_ALGORITHMS)
            registry = JWTClaimsRegistry(
                now=int(self._clock().timestamp()),
                iss={"essential": True, "value": self._config.issuer},
                aud={"essential": True, "value": self._config.resource},
                exp={"essential": True},
            )
            registry.validate(decoded.claims)
        except (JoseError, ValueError):
            return None
        claims = decoded.claims
        return VerifiedAccessToken(
            subject=claims["sub"],
            client_id=claims.get("client_id", ""),
            scope=claims.get("scope", ""),
            audience=claims["aud"],
            jti=claims.get("jti", ""),
        )


def mint_refresh_token() -> str:
    """A high-entropy opaque refresh token (the value returned to the client)."""
    return secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """SHA-256 hex digest stored at rest, so the raw refresh token is never persisted."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
