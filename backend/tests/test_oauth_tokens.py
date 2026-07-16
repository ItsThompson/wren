"""Access-token minting/verification, PKCE S256, and refresh-token hashing.

Proves the security-critical token properties the RS depends on: RS256 signature,
issuer + audience binding to the MCP resource, expiry, and that a tampered or
foreign-audience token fails verification. PKCE and refresh-hash helpers are
covered here too.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from tests.oauth_fakes import (
    MutableClock,
    build_test_codec,
    build_test_config,
    build_test_keyset,
    make_pkce_pair,
)
from wren.oauth.injection import Clock, utcnow
from wren.oauth.pkce import is_valid_s256
from wren.oauth.tokens import hash_token, mint_refresh_token

if TYPE_CHECKING:
    from wren.oauth.config import OAuthConfig
    from wren.oauth.tokens import AccessTokenCodec


def _codec(
    *, clock: Clock = utcnow, **config_overrides: object
) -> tuple[AccessTokenCodec, OAuthConfig]:
    config = build_test_config(**config_overrides)  # type: ignore[arg-type]
    return build_test_codec(config, build_test_keyset(config), clock=clock), config


def test_minted_access_token_verifies_with_the_expected_claims() -> None:
    codec, config = _codec()
    minted = codec.mint(
        subject="user-1", client_id="client-1", scope="roadmaps:read", audience=config.resource
    )
    verified = codec.verify(minted.token)
    assert verified is not None
    assert verified.subject == "user-1"
    assert verified.client_id == "client-1"
    assert verified.scope == "roadmaps:read"
    assert verified.audience == config.resource
    assert minted.expires_in == int(config.access_ttl.total_seconds())


def test_access_token_is_audience_bound_to_the_mcp_resource() -> None:
    codec, _ = _codec()
    # A token minted for a different audience must not verify against our resource.
    minted = codec.mint(
        subject="user-1",
        client_id="client-1",
        scope="roadmaps:read",
        audience="https://evil.example",
    )
    assert codec.verify(minted.token) is None


def test_expired_access_token_fails_verification() -> None:
    # Pinned clock: mint at t0, advance past the TTL, then verify against the same
    # clock (no negative timedelta).
    clock = MutableClock(datetime(2024, 1, 1, tzinfo=UTC))
    codec, config = _codec(access_ttl=timedelta(minutes=15), clock=clock)
    minted = codec.mint(
        subject="user-1", client_id="client-1", scope="roadmaps:read", audience=config.resource
    )
    assert codec.verify(minted.token) is not None  # valid before the TTL elapses
    clock.advance(timedelta(minutes=16))
    assert codec.verify(minted.token) is None  # expired after


def test_tampered_access_token_fails_verification() -> None:
    codec, config = _codec()
    minted = codec.mint(
        subject="user-1", client_id="client-1", scope="roadmaps:read", audience=config.resource
    )
    tampered = minted.token[:-3] + ("aaa" if not minted.token.endswith("aaa") else "bbb")
    assert codec.verify(tampered) is None


def test_token_signed_by_a_foreign_key_fails_verification() -> None:
    codec_a, config = _codec()
    codec_b = build_test_codec(config, build_test_keyset(config))  # different ephemeral key
    minted = codec_b.mint(
        subject="user-1", client_id="client-1", scope="roadmaps:read", audience=config.resource
    )
    assert codec_a.verify(minted.token) is None


def test_pkce_s256_accepts_the_matching_verifier() -> None:
    verifier, challenge = make_pkce_pair()
    assert is_valid_s256(verifier, challenge) is True


def test_pkce_s256_rejects_a_wrong_verifier_and_empty_input() -> None:
    _verifier, challenge = make_pkce_pair()
    assert is_valid_s256("not-the-verifier", challenge) is False
    assert is_valid_s256("", challenge) is False
    assert is_valid_s256("x", "") is False


def test_refresh_token_hash_is_stable_and_hides_the_raw_token() -> None:
    raw = mint_refresh_token()
    assert hash_token(raw) == hash_token(raw)
    assert raw not in hash_token(raw)
    assert len(hash_token(raw)) == 64  # sha256 hex
    assert mint_refresh_token() != mint_refresh_token()  # high-entropy, unique
