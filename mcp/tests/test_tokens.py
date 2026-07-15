"""Token-validation tests: the RS's agent trust boundary (spec section 08).

A token is accepted only if its signature verifies against the AS JWKS and its
``iss``/``aud``/``exp`` claims hold; anything else resolves to ``None`` (rejected).
Uses the real :class:`RemoteKeyProvider` with a faked JWKS fetch (sociable): only
the network is substituted, the joserfc crypto path runs for real.
"""

from __future__ import annotations

import pytest

from token_factory import ISSUER, RESOURCE, make_fetch, mint, new_key, public_jwks
from wren_mcp.keys import RemoteKeyProvider
from wren_mcp.tokens import AgentTokenVerifier


def _verifier(jwks_keys: list, fetch=None) -> AgentTokenVerifier:
    key_provider = RemoteKeyProvider(ISSUER, fetch or make_fetch(public_jwks(*jwks_keys)))
    return AgentTokenVerifier(key_provider, issuer=ISSUER, resource=RESOURCE)


async def test_valid_token_resolves_to_a_single_user_id() -> None:
    key = new_key()
    verifier = _verifier([key])
    token = mint(key, sub="user-ada", scope="roadmaps:read", client_id="agent-1")

    principal = await verifier.verify(token)

    assert principal is not None
    assert principal.user_id == "user-ada"
    assert principal.client_id == "agent-1"
    assert principal.scope == "roadmaps:read"


async def test_token_for_a_different_audience_is_rejected() -> None:
    # Audience binding (confused-deputy defense): a well-signed token minted for
    # another resource must not be accepted by this RS.
    key = new_key()
    verifier = _verifier([key])
    token = mint(key, aud="https://someone-else.example")

    assert await verifier.verify(token) is None


async def test_token_signed_by_an_unknown_key_is_rejected() -> None:
    # The JWKS advertises `served`, but the token is signed by `attacker` under
    # the same kid: the signature cannot verify against the published key.
    served = new_key(kid="kid-1")
    attacker = new_key(kid="kid-1")
    verifier = _verifier([served])
    token = mint(attacker)

    assert await verifier.verify(token) is None


async def test_expired_token_is_rejected() -> None:
    key = new_key()
    verifier = _verifier([key])
    token = mint(key, exp_offset=-60)

    assert await verifier.verify(token) is None


async def test_token_from_a_different_issuer_is_rejected() -> None:
    key = new_key()
    verifier = _verifier([key])
    token = mint(key, issuer="https://evil.example")

    assert await verifier.verify(token) is None


async def test_token_without_a_subject_is_rejected() -> None:
    key = new_key()
    verifier = _verifier([key])
    token = mint(key, sub=None)

    assert await verifier.verify(token) is None


@pytest.mark.parametrize("garbage", ["", "not-a-jwt", "a.b", "Bearer x.y.z"])
async def test_malformed_token_is_rejected(garbage: str) -> None:
    key = new_key()
    verifier = _verifier([key])

    assert await verifier.verify(garbage) is None


async def test_rotated_kid_is_accepted_after_a_refetch() -> None:
    # The AS rotated its signing key; the RS's cache still holds the old key. A
    # token under the new kid triggers one JWKS refetch, then verifies.
    old_key = new_key(kid="kid-old")
    new_signing = new_key(kid="kid-new")
    fetch = make_fetch(public_jwks(old_key))
    key_provider = RemoteKeyProvider(ISSUER, fetch, refresh_cooldown_seconds=0.0)
    verifier = AgentTokenVerifier(key_provider, issuer=ISSUER, resource=RESOURCE)

    # Prime the cache with the old key set, then rotate the served JWKS.
    assert await verifier.verify(mint(old_key)) is not None
    fetch_after_rotation = make_fetch(public_jwks(old_key, new_signing))
    key_provider._fetch_json = fetch_after_rotation  # type: ignore[attr-defined]

    principal = await verifier.verify(mint(new_signing))

    assert principal is not None
    assert principal.user_id == "user-ada"
