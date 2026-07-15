"""Session token codec: HS256 mint/verify, type separation, expiry, tamper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from accounts_fakes import TEST_SESSION_SECRET, build_test_codec
from wren.accounts.config import SessionConfig
from wren.accounts.tokens import SessionTokenCodec


def test_mint_pair_shares_one_session_id() -> None:
    codec = build_test_codec()
    pair = codec.mint_pair("user-1")
    access = codec.verify_access(pair.access_token)
    refresh = codec.verify_refresh(pair.refresh_token)
    assert access is not None and refresh is not None
    # Access + refresh belong to the same session so revoking the sid kills both.
    assert access.sid == refresh.sid == pair.sid
    assert access.user_id == refresh.user_id == "user-1"


def test_max_ages_track_the_configured_ttls() -> None:
    codec = build_test_codec(access_ttl=timedelta(minutes=15), refresh_ttl=timedelta(days=14))
    pair = codec.mint_pair("user-1")
    assert pair.access_max_age == 15 * 60
    assert pair.refresh_max_age == 14 * 24 * 3600


def test_access_token_is_not_accepted_as_refresh_and_vice_versa() -> None:
    codec = build_test_codec()
    pair = codec.mint_pair("user-1")
    # An access token must not pass refresh verification (different `type` claim).
    assert codec.verify_refresh(pair.access_token) is None
    assert codec.verify_access(pair.refresh_token) is None


def test_expired_access_token_does_not_verify() -> None:
    codec = build_test_codec(access_ttl=timedelta(seconds=-1))
    pair = codec.mint_pair("user-1")
    assert codec.verify_access(pair.access_token) is None


def test_expired_refresh_token_does_not_verify() -> None:
    codec = build_test_codec(refresh_ttl=timedelta(seconds=-1))
    pair = codec.mint_pair("user-1")
    assert codec.verify_refresh(pair.refresh_token) is None


def test_token_signed_with_a_different_secret_is_rejected() -> None:
    minted = SessionTokenCodec(SessionConfig(secret="other-secret")).mint_pair("user-1")
    verifier = build_test_codec()
    assert verifier.verify_access(minted.access_token) is None


def test_tampered_token_is_rejected() -> None:
    codec = build_test_codec()
    pair = codec.mint_pair("user-1")
    tampered = pair.access_token[:-2] + ("aa" if pair.access_token[-2:] != "aa" else "bb")
    assert codec.verify_access(tampered) is None


def test_garbage_string_is_rejected() -> None:
    assert build_test_codec().verify_access("not.a.jwt") is None


def test_refresh_claims_carry_expiry_for_the_blacklist() -> None:
    codec = build_test_codec()
    pair = codec.mint_pair("user-1")
    claims = codec.verify_refresh(pair.refresh_token)
    assert claims is not None
    assert claims.expires_at == pair.refresh_expires_at.replace(microsecond=0)


@pytest.mark.parametrize("field", ["sub", "sid", "type"])
def test_token_missing_a_required_claim_is_rejected(field: str) -> None:
    payload = {
        "sub": "user-1",
        "sid": "s1",
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    del payload[field]
    forged = jwt.encode(payload, TEST_SESSION_SECRET, algorithm="HS256")
    assert build_test_codec().verify_access(forged) is None
