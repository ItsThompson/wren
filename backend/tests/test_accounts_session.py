"""The composed session verifier: valid access -> user_id, revoked/invalid -> None."""

from __future__ import annotations

from accounts_fakes import build_test_codec
from wren.accounts.session import create_session_verifier


async def _never_revoked(_sid: str) -> bool:
    return False


async def test_verifier_resolves_a_valid_access_token_to_its_user() -> None:
    codec = build_test_codec()
    pair = codec.mint_pair("user-1")
    verify = create_session_verifier(codec, _never_revoked)
    assert await verify(pair.access_token) == "user-1"


async def test_verifier_denies_a_revoked_session() -> None:
    codec = build_test_codec()
    pair = codec.mint_pair("user-1")

    async def revoked(sid: str) -> bool:
        return sid == pair.sid

    verify = create_session_verifier(codec, revoked)
    # The token is cryptographically valid but its sid is blacklisted.
    assert await verify(pair.access_token) is None


async def test_verifier_denies_an_invalid_token_without_checking_revocation() -> None:
    checked: list[str] = []

    async def spy(sid: str) -> bool:
        checked.append(sid)
        return False

    verify = create_session_verifier(build_test_codec(), spy)
    assert await verify("not-a-jwt") is None
    # An unverifiable token short-circuits before the blacklist lookup.
    assert checked == []
