"""Token-validation tests: the RS's agent trust boundary.

A token is accepted only if its signature verifies against the AS JWKS and its
``iss``/``aud``/``exp`` claims hold; anything else resolves to ``None`` (rejected).
Uses the real :class:`RemoteKeyProvider` with a faked JWKS fetch (sociable): only
the network is substituted, the joserfc crypto path runs for real.
"""

from __future__ import annotations

import base64
import json
import time
import warnings
from typing import TYPE_CHECKING

import pytest
from joserfc import jwt
from joserfc.jwk import OctKey, RSAKey

from token_factory import ISSUER, RESOURCE, make_fetch, mint, new_key, public_jwks
from wren_mcp.keys import RemoteKeyProvider
from wren_mcp.tokens import AgentTokenVerifier

if TYPE_CHECKING:
    from wren_mcp.keys import JsonFetch


def _verifier(jwks_keys: list[RSAKey], fetch: JsonFetch | None = None) -> AgentTokenVerifier:
    key_provider = RemoteKeyProvider(ISSUER, fetch or make_fetch(public_jwks(*jwks_keys)))
    return AgentTokenVerifier(key_provider, issuer=ISSUER, resource=RESOURCE)


def _b64url(payload: dict[str, object]) -> str:
    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _valid_claims() -> dict[str, object]:
    # Legitimate iss/aud/sub/exp, so the ONLY illegitimate thing about the attack
    # tokens below is the algorithm: rejection must come from the RS256 pin.
    now = int(time.time())
    return {"iss": ISSUER, "aud": RESOURCE, "sub": "user-ada", "iat": now, "exp": now + 3600}


def _alg_none_token(kid: str) -> str:
    """An unsigned ``alg=none`` token (RFC 7515) with an empty signature."""
    header = _b64url({"alg": "none", "kid": kid})
    return f"{header}.{_b64url(_valid_claims())}."


def _hs256_confusion_token(rsa_key: RSAKey) -> str:
    """The RS256/HS256 confusion attack: an HMAC-SHA256 token signed with the RSA
    *public* key bytes as the shared secret, under the served ``kid``. A verifier
    that trusted the header's ``alg`` would accept it."""
    public_pem = rsa_key.as_pem(private=False)
    with warnings.catch_warnings():
        # joserfc warns when a PEM is imported as an oct key; that is exactly the
        # attacker's misuse we are simulating, so silence it for a clean run.
        warnings.simplefilter("ignore")
        secret = OctKey.import_key(public_pem)
    return jwt.encode({"alg": "HS256", "kid": str(rsa_key.kid)}, _valid_claims(), secret)


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
    key_provider._fetch_json = fetch_after_rotation

    principal = await verifier.verify(mint(new_signing))

    assert principal is not None
    assert principal.user_id == "user-ada"


async def test_alg_none_token_is_rejected() -> None:
    # Algorithm substitution (unsigned token): pins that the RS256 allowlist
    # rejects `alg=none` even with otherwise-valid claims. If someone later widens
    # the algorithm list, this fails instead of silently reintroducing the vuln.
    key = new_key(kid="kid-1")
    verifier = _verifier([key])

    assert await verifier.verify(_alg_none_token("kid-1")) is None


async def test_hs256_rs256_algorithm_confusion_is_rejected() -> None:
    # The canonical JWKS attack: a token signed HS256 with the RSA public key as
    # the HMAC secret. The RS256 pin must reject it; a verifier that honored the
    # header's alg would treat the public key as a shared secret and accept it.
    key = new_key(kid="kid-1")
    verifier = _verifier([key])

    assert await verifier.verify(_hs256_confusion_token(key)) is None
