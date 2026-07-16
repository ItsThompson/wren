"""Test support: mint AS-shaped tokens and serve a fake JWKS discovery.

Keeps the RS tests self-contained (no dependency on the backend AS package): a
throwaway RSA key stands in for the AS signing key, ``public_jwks`` is what the
RS would fetch, and :func:`make_fetch` fakes the two discovery hops (AS metadata
-> JWKS) the :class:`~wren_mcp.keys.RemoteKeyProvider` performs.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

from wren_mcp.config import AS_METADATA_PATH

if TYPE_CHECKING:
    from wren_mcp.keys import JsonFetch

ISSUER = "https://api.usewren.com"
RESOURCE = "https://mcp.usewren.com"
JWKS_URI = f"{ISSUER}/jwks"

_KEY_BITS = 2048


def new_key(kid: str = "kid-test-1") -> RSAKey:
    """A fresh RSA signing key tagged for RS256, mirroring the AS key set."""
    return RSAKey.generate_key(
        _KEY_BITS, parameters={"use": "sig", "alg": "RS256", "kid": kid}, private=True
    )


def public_jwks(*keys: RSAKey) -> dict[str, Any]:
    """The public JWKS document the AS would publish for the given keys."""
    return dict(KeySet(list(keys)).as_dict(private=False))


def mint(
    key: RSAKey,
    *,
    sub: str | None = "user-ada",
    issuer: str = ISSUER,
    aud: str = RESOURCE,
    kid: str | None = None,
    client_id: str = "agent-client",
    scope: str = "roadmaps:read roadmaps:write",
    exp_offset: int = 3600,
) -> str:
    """Sign an access token like the AS does (RS256, audience-bound)."""
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": issuer,
        "aud": aud,
        "client_id": client_id,
        "scope": scope,
        "iat": now,
        "exp": now + exp_offset,
    }
    if sub is not None:
        claims["sub"] = sub
    header = {"alg": "RS256", "kid": kid or str(key.kid)}
    return jwt.encode(header, claims, key)


def make_fetch(
    jwks: dict[str, Any], *, issuer: str = ISSUER, jwks_uri: str = JWKS_URI
) -> JsonFetch:
    """A ``JsonFetch`` that serves AS metadata + the given JWKS, tracking calls.

    ``fetch.calls`` records every URL fetched so tests can assert caching (one
    discovery pass) and rotation (a refetch on an unknown ``kid``).
    """
    metadata = {"issuer": issuer, "jwks_uri": jwks_uri}

    async def fetch(url: str) -> dict[str, Any]:
        fetch.calls.append(url)  # type: ignore[attr-defined]
        if url == f"{issuer}{AS_METADATA_PATH}":
            return metadata
        if url == jwks_uri:
            return jwks
        raise AssertionError(f"unexpected fetch url: {url}")

    fetch.calls = []  # type: ignore[attr-defined]
    return fetch
