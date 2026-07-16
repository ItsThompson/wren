"""Sociable service tests: the full Authlib-backed AS flow in-process.

Exercises the real :class:`AuthorizationService` + :class:`TokenService` over the
in-memory repository with real signing keys and PKCE: DCR -> authorize-park ->
PKCE ``/token`` -> refresh rotation -> ``/revoke`` -> audience binding, plus the
downgrade/mismatch/replay/expiry failure paths.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from oauth_fakes import (
    InMemoryOAuthRepository,
    MutableClock,
    build_test_codec,
    build_test_config,
    build_test_keyset,
    make_pkce_pair,
)
from wren.core.errors import NotFound
from wren.core.observability import WREN_REGISTRY
from wren.oauth.authorization import AuthorizationService
from wren.oauth.config import OAuthConfig
from wren.oauth.errors import OAuthError, OAuthErrorCode
from wren.oauth.injection import Clock, utcnow
from wren.oauth.schemas import (
    AuthorizeParams,
    ClientRegistrationRequest,
    OAuthEvent,
    TokenRequest,
)
from wren.oauth.token_exchange import TokenService
from wren.oauth.tokens import AccessTokenCodec

_USER = "user-ada"
_REDIRECT = "http://127.0.0.1:8765/callback"


@dataclass
class Harness:
    auth: AuthorizationService
    tokens: TokenService
    repo: InMemoryOAuthRepository
    config: OAuthConfig
    codec: AccessTokenCodec


def _harness(
    *,
    clock: Clock = utcnow,
    issued_counter: Callable[[str], None] | None = None,
    **config_overrides: object,
) -> Harness:
    config = build_test_config(**config_overrides)  # type: ignore[arg-type]
    codec = build_test_codec(config, build_test_keyset(config), clock=clock)
    repo = InMemoryOAuthRepository()
    tokens = (
        TokenService(repo, config, codec, clock=clock)
        if issued_counter is None
        else TokenService(repo, config, codec, clock=clock, issued_counter=issued_counter)
    )
    return Harness(
        auth=AuthorizationService(repo, config, clock=clock),
        tokens=tokens,
        repo=repo,
        config=config,
        codec=codec,
    )


async def _register(auth: AuthorizationService, *, scope: str | None = None) -> str:
    response = await auth.register_client(
        ClientRegistrationRequest(redirect_uris=[_REDIRECT], client_name="Test Agent", scope=scope)
    )
    return response.client_id


def _query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


async def _park(auth: AuthorizationService, client_id: str, challenge: str, **overrides: object):
    fields: dict[str, object] = {
        "client_id": client_id,
        "redirect_uri": _REDIRECT,
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "xyz",
    }
    fields.update(overrides)
    consent_url = await auth.start_authorization(AuthorizeParams(**fields))  # type: ignore[arg-type]
    return _query(consent_url)["auth_request_id"]


async def _authorize_to_code(harness: Harness, client_id: str, challenge: str) -> str:
    request_id = await _park(harness.auth, client_id, challenge)
    redirect = await harness.auth.decide(auth_request_id=request_id, user_id=_USER, approve=True)
    return _query(redirect)["code"]


# --- Dynamic Client Registration --------------------------------------------


async def test_register_mints_a_public_client_with_defaults() -> None:
    h = _harness()
    response = await h.auth.register_client(
        ClientRegistrationRequest(redirect_uris=[_REDIRECT], client_name="Agent")
    )
    assert response.client_id
    assert response.token_endpoint_auth_method == "none"
    assert response.grant_types == ["authorization_code", "refresh_token"]
    assert response.response_types == ["code"]
    assert set(response.scope.split()) == {"roadmaps:read", "roadmaps:write", "progress:write"}
    assert await h.repo.get_client(response.client_id) is not None


async def test_register_rejects_non_loopback_http_redirect() -> None:
    h = _harness()
    with pytest.raises(OAuthError) as exc:
        await h.auth.register_client(
            ClientRegistrationRequest(redirect_uris=["http://evil.example.com/cb"])
        )
    assert exc.value.error == OAuthErrorCode.INVALID_CLIENT_METADATA


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "javascript:alert(document.cookie)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "com.evil.app:/callback",
        "http://evil.example.com/cb",
        "https:",
        "https:///onlypath",
        "/callback",
    ],
)
async def test_register_rejects_dangerous_or_non_allowlisted_redirects(redirect_uri: str) -> None:
    # Allowlist: only https-with-a-host or loopback http may register. A dangerous
    # scheme (javascript:/data:/file:), an arbitrary custom/non-loopback scheme,
    # or a degenerate hostless https URI is rejected at DCR so it can never become
    # a consent navigation target.
    h = _harness()
    with pytest.raises(OAuthError) as exc:
        await h.auth.register_client(ClientRegistrationRequest(redirect_uris=[redirect_uri]))
    assert exc.value.error == OAuthErrorCode.INVALID_CLIENT_METADATA


async def test_register_accepts_https_and_loopback_http_redirects() -> None:
    h = _harness()
    response = await h.auth.register_client(
        ClientRegistrationRequest(
            redirect_uris=["https://app.example.com/callback", "http://127.0.0.1:9000/cb"]
        )
    )
    assert response.client_id


async def test_register_rejects_relative_redirect() -> None:
    h = _harness()
    with pytest.raises(OAuthError):
        await h.auth.register_client(ClientRegistrationRequest(redirect_uris=["/callback"]))


# --- authorize (validation + parking) ---------------------------------------


async def test_start_authorization_parks_and_returns_the_consent_url() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    _verifier, challenge = make_pkce_pair()
    consent_url = await h.auth.start_authorization(
        AuthorizeParams(
            client_id=client_id,
            redirect_uri=_REDIRECT,
            response_type="code",
            code_challenge=challenge,
            code_challenge_method="S256",
            state="xyz",
        )
    )
    assert consent_url.startswith("https://usewren.com/authorize?")
    request_id = _query(consent_url)["auth_request_id"]
    assert await h.repo.get_auth_request(request_id) is not None


async def test_authorize_rejects_unknown_client() -> None:
    h = _harness()
    _verifier, challenge = make_pkce_pair()
    with pytest.raises(OAuthError) as exc:
        await _park(h.auth, "no-such-client", challenge)
    assert exc.value.error == OAuthErrorCode.INVALID_CLIENT


async def test_authorize_rejects_unregistered_redirect_uri() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    _verifier, challenge = make_pkce_pair()
    with pytest.raises(OAuthError) as exc:
        await _park(h.auth, client_id, challenge, redirect_uri="https://evil.example/cb")
    assert exc.value.error == OAuthErrorCode.INVALID_REQUEST


async def test_authorize_requires_s256_pkce() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    with pytest.raises(OAuthError) as exc:
        await _park(h.auth, client_id, "", code_challenge_method="plain")
    assert exc.value.error == OAuthErrorCode.INVALID_REQUEST


async def test_authorize_rejects_response_type_other_than_code() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    _verifier, challenge = make_pkce_pair()
    with pytest.raises(OAuthError):
        await _park(h.auth, client_id, challenge, response_type="token")


async def test_authorize_rejects_scope_not_granted_to_client() -> None:
    h = _harness()
    client_id = await _register(h.auth, scope="roadmaps:read")
    _verifier, challenge = make_pkce_pair()
    with pytest.raises(OAuthError) as exc:
        await _park(h.auth, client_id, challenge, scope="roadmaps:write")
    assert exc.value.error == OAuthErrorCode.INVALID_SCOPE


async def test_authorize_accepts_an_explicit_granted_subset_scope() -> None:
    h = _harness()
    client_id = await _register(h.auth)  # granted all supported scopes
    _verifier, challenge = make_pkce_pair()
    request_id = await _park(h.auth, client_id, challenge, scope="roadmaps:read")
    parked = await h.repo.get_auth_request(request_id)
    assert parked is not None and parked.scope == "roadmaps:read"


async def test_authorize_rejects_an_unsupported_scope() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    _verifier, challenge = make_pkce_pair()
    with pytest.raises(OAuthError) as exc:
        await _park(h.auth, client_id, challenge, scope="admin:everything")
    assert exc.value.error == OAuthErrorCode.INVALID_SCOPE


async def test_authorize_rejects_foreign_resource() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    _verifier, challenge = make_pkce_pair()
    with pytest.raises(OAuthError) as exc:
        await _park(h.auth, client_id, challenge, resource="https://evil.example")
    assert exc.value.error == OAuthErrorCode.INVALID_TARGET


# --- consent context + decision ---------------------------------------------


async def test_get_context_returns_client_name_scopes_and_auth_flag() -> None:
    h = _harness()
    client_id = await _register(h.auth, scope="roadmaps:read progress:write")
    _verifier, challenge = make_pkce_pair()
    request_id = await _park(h.auth, client_id, challenge)
    context = await h.auth.get_context(request_id, authenticated=False)
    assert context.client_name == "Test Agent"
    assert set(context.scopes) == {"roadmaps:read", "progress:write"}
    assert context.authenticated is False


async def test_get_context_for_missing_request_is_not_found() -> None:
    h = _harness()
    with pytest.raises(NotFound):
        await h.auth.get_context("nope", authenticated=True)


async def test_deny_returns_access_denied_and_mints_no_code() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    _verifier, challenge = make_pkce_pair()
    request_id = await _park(h.auth, client_id, challenge)
    redirect = await h.auth.decide(auth_request_id=request_id, user_id=_USER, approve=False)
    params = _query(redirect)
    assert params["error"] == "access_denied"
    assert params["state"] == "xyz"
    assert "code" not in params
    assert await h.repo.get_grant(_USER, client_id) is None


async def test_decision_consumes_the_parked_request() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    _verifier, challenge = make_pkce_pair()
    request_id = await _park(h.auth, client_id, challenge)
    await h.auth.decide(auth_request_id=request_id, user_id=_USER, approve=True)
    # The one-time request is gone: a replayed decision cannot re-approve.
    with pytest.raises(NotFound):
        await h.auth.decide(auth_request_id=request_id, user_id=_USER, approve=True)


async def test_approve_records_grant_and_audit() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    _verifier, challenge = make_pkce_pair()
    request_id = await _park(h.auth, client_id, challenge)
    redirect = await h.auth.decide(auth_request_id=request_id, user_id=_USER, approve=True)
    assert _query(redirect)["state"] == "xyz"
    assert await h.repo.get_grant(_USER, client_id) is not None
    assert any(e.event == OAuthEvent.GRANTED.value for e in h.repo.audit)


async def test_decision_without_state_omits_state_in_the_redirect() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    _verifier, challenge = make_pkce_pair()
    # Approve with no `state` in the original request: the loopback URL carries a
    # code but no state parameter.
    approve_request = await _park(h.auth, client_id, challenge, state=None)
    approve = await h.auth.decide(auth_request_id=approve_request, user_id=_USER, approve=True)
    assert "code" in _query(approve) and "state" not in _query(approve)
    # Deny with no `state`: access_denied and no state parameter.
    deny_request = await _park(h.auth, client_id, challenge, state=None)
    deny = await h.auth.decide(auth_request_id=deny_request, user_id=_USER, approve=False)
    assert _query(deny)["error"] == "access_denied" and "state" not in _query(deny)


async def test_expired_parked_request_is_not_found() -> None:
    clock = MutableClock(datetime(2024, 1, 1, tzinfo=UTC))
    h = _harness(clock=clock, auth_request_ttl=timedelta(minutes=10))
    client_id = await _register(h.auth)
    _verifier, challenge = make_pkce_pair()
    request_id = await _park(h.auth, client_id, challenge)
    # Advance a pinned clock past the TTL instead of parking with a negative one.
    clock.advance(timedelta(minutes=11))
    with pytest.raises(NotFound):
        await h.auth.get_context(request_id, authenticated=True)


# --- token exchange (authorization_code + PKCE) -----------------------------


async def test_code_exchange_returns_audience_bound_access_and_refresh() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    verifier, challenge = make_pkce_pair()
    code = await _authorize_to_code(h, client_id, challenge)

    result = await h.tokens.exchange(
        TokenRequest(
            grant_type="authorization_code",
            client_id=client_id,
            code=code,
            code_verifier=verifier,
            redirect_uri=_REDIRECT,
        )
    )
    assert result.token_type == "Bearer"
    assert result.refresh_token
    verified = h.codec.verify(result.access_token)
    assert verified is not None
    assert verified.subject == _USER
    assert verified.audience == h.config.resource
    assert any(e.event == OAuthEvent.TOKEN_ISSUED.value for e in h.repo.audit)


async def test_code_exchange_rejects_wrong_pkce_verifier() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    _verifier, challenge = make_pkce_pair()
    code = await _authorize_to_code(h, client_id, challenge)
    with pytest.raises(OAuthError) as exc:
        await h.tokens.exchange(
            TokenRequest(
                grant_type="authorization_code",
                client_id=client_id,
                code=code,
                code_verifier="wrong-verifier",
                redirect_uri=_REDIRECT,
            )
        )
    assert exc.value.error == OAuthErrorCode.INVALID_GRANT


async def test_code_exchange_rejects_a_revoked_grant() -> None:
    # Revocation must win a race with an outstanding code: a code minted before
    # the user revoked the client cannot mint a fresh, un-revoked refresh token
    # within the code TTL.
    h = _harness()
    client_id = await _register(h.auth)
    verifier, challenge = make_pkce_pair()
    code = await _authorize_to_code(h, client_id, challenge)
    await h.tokens.revoke_connected_client(_USER, client_id)
    with pytest.raises(OAuthError) as exc:
        await h.tokens.exchange(
            TokenRequest(
                grant_type="authorization_code",
                client_id=client_id,
                code=code,
                code_verifier=verifier,
                redirect_uri=_REDIRECT,
            )
        )
    assert exc.value.error == OAuthErrorCode.INVALID_GRANT


async def test_authorization_code_is_single_use() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    verifier, challenge = make_pkce_pair()
    code = await _authorize_to_code(h, client_id, challenge)
    request = TokenRequest(
        grant_type="authorization_code",
        client_id=client_id,
        code=code,
        code_verifier=verifier,
        redirect_uri=_REDIRECT,
    )
    await h.tokens.exchange(request)
    with pytest.raises(OAuthError) as exc:
        await h.tokens.exchange(request)
    assert exc.value.error == OAuthErrorCode.INVALID_GRANT


async def test_code_exchange_rejects_client_mismatch() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    other_client = await _register(h.auth)
    verifier, challenge = make_pkce_pair()
    code = await _authorize_to_code(h, client_id, challenge)
    with pytest.raises(OAuthError) as exc:
        await h.tokens.exchange(
            TokenRequest(
                grant_type="authorization_code",
                client_id=other_client,
                code=code,
                code_verifier=verifier,
                redirect_uri=_REDIRECT,
            )
        )
    assert exc.value.error == OAuthErrorCode.INVALID_GRANT


async def test_code_exchange_rejects_redirect_uri_mismatch() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    verifier, challenge = make_pkce_pair()
    code = await _authorize_to_code(h, client_id, challenge)
    with pytest.raises(OAuthError):
        await h.tokens.exchange(
            TokenRequest(
                grant_type="authorization_code",
                client_id=client_id,
                code=code,
                code_verifier=verifier,
                redirect_uri="http://127.0.0.1:1/other",
            )
        )


async def test_code_exchange_rejects_foreign_resource() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    verifier, challenge = make_pkce_pair()
    code = await _authorize_to_code(h, client_id, challenge)
    with pytest.raises(OAuthError) as exc:
        await h.tokens.exchange(
            TokenRequest(
                grant_type="authorization_code",
                client_id=client_id,
                code=code,
                code_verifier=verifier,
                redirect_uri=_REDIRECT,
                resource="https://evil.example",
            )
        )
    assert exc.value.error == OAuthErrorCode.INVALID_TARGET


async def test_expired_code_is_rejected() -> None:
    clock = MutableClock(datetime(2024, 1, 1, tzinfo=UTC))
    h = _harness(clock=clock, code_ttl=timedelta(minutes=1))
    client_id = await _register(h.auth)
    verifier, challenge = make_pkce_pair()
    code = await _authorize_to_code(h, client_id, challenge)
    # Advance past the code TTL via the pinned clock (no negative timedelta).
    clock.advance(timedelta(minutes=2))
    with pytest.raises(OAuthError) as exc:
        await h.tokens.exchange(
            TokenRequest(
                grant_type="authorization_code",
                client_id=client_id,
                code=code,
                code_verifier=verifier,
                redirect_uri=_REDIRECT,
            )
        )
    assert exc.value.error == OAuthErrorCode.INVALID_GRANT


async def test_unsupported_grant_type_is_rejected() -> None:
    h = _harness()
    with pytest.raises(OAuthError) as exc:
        await h.tokens.exchange(TokenRequest(grant_type="password"))
    assert exc.value.error == OAuthErrorCode.UNSUPPORTED_GRANT_TYPE


async def test_code_exchange_requires_code_verifier_and_client_id() -> None:
    h = _harness()
    with pytest.raises(OAuthError) as exc:
        await h.tokens.exchange(
            TokenRequest(grant_type="authorization_code", code="c", client_id="x")
        )
    assert exc.value.error == OAuthErrorCode.INVALID_REQUEST


# --- refresh rotation + replay ----------------------------------------------


async def _issue_tokens(h: Harness, client_id: str):
    verifier, challenge = make_pkce_pair()
    code = await _authorize_to_code(h, client_id, challenge)
    return await h.tokens.exchange(
        TokenRequest(
            grant_type="authorization_code",
            client_id=client_id,
            code=code,
            code_verifier=verifier,
            redirect_uri=_REDIRECT,
        )
    )


async def test_refresh_rotates_and_issues_a_new_pair() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    first = await _issue_tokens(h, client_id)
    rotated = await h.tokens.exchange(
        TokenRequest(
            grant_type="refresh_token", client_id=client_id, refresh_token=first.refresh_token
        )
    )
    assert rotated.refresh_token != first.refresh_token
    assert h.codec.verify(rotated.access_token) is not None
    assert any(e.event == OAuthEvent.REFRESHED.value for e in h.repo.audit)


def _issued_count(grant_type: str) -> float:
    value = WREN_REGISTRY.get_sample_value("oauth_tokens_issued_total", {"grant_type": grant_type})
    return value or 0.0


async def test_issuance_and_refresh_increment_the_domain_counter() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    code_before = _issued_count("authorization_code")
    refresh_before = _issued_count("refresh_token")

    first = await _issue_tokens(h, client_id)
    await h.tokens.exchange(
        TokenRequest(
            grant_type="refresh_token", client_id=client_id, refresh_token=first.refresh_token
        )
    )

    # A code exchange is one authorization_code issuance; the rotation is one
    # refresh_token issuance.
    assert _issued_count("authorization_code") == code_before + 1
    assert _issued_count("refresh_token") == refresh_before + 1


async def test_rotated_refresh_token_replay_is_rejected_and_revokes_chain() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    first = await _issue_tokens(h, client_id)
    rotated = await h.tokens.exchange(
        TokenRequest(
            grant_type="refresh_token", client_id=client_id, refresh_token=first.refresh_token
        )
    )
    # Reusing the old (already-rotated) refresh token is a replay: rejected...
    with pytest.raises(OAuthError) as exc:
        await h.tokens.exchange(
            TokenRequest(
                grant_type="refresh_token", client_id=client_id, refresh_token=first.refresh_token
            )
        )
    assert exc.value.error == OAuthErrorCode.INVALID_GRANT
    # ...and the whole chain is revoked, so even the freshly rotated token dies.
    with pytest.raises(OAuthError):
        await h.tokens.exchange(
            TokenRequest(
                grant_type="refresh_token", client_id=client_id, refresh_token=rotated.refresh_token
            )
        )


async def test_refresh_rejects_client_mismatch() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    other = await _register(h.auth)
    first = await _issue_tokens(h, client_id)
    with pytest.raises(OAuthError) as exc:
        await h.tokens.exchange(
            TokenRequest(
                grant_type="refresh_token", client_id=other, refresh_token=first.refresh_token
            )
        )
    assert exc.value.error == OAuthErrorCode.INVALID_GRANT


async def test_refresh_rejects_unknown_token() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    with pytest.raises(OAuthError):
        await h.tokens.exchange(
            TokenRequest(grant_type="refresh_token", client_id=client_id, refresh_token="nope")
        )


async def test_refresh_requires_refresh_token_and_client_id() -> None:
    h = _harness()
    with pytest.raises(OAuthError) as exc:
        await h.tokens.exchange(TokenRequest(grant_type="refresh_token", client_id="x"))
    assert exc.value.error == OAuthErrorCode.INVALID_REQUEST


async def test_expired_refresh_token_is_rejected() -> None:
    clock = MutableClock(datetime(2024, 1, 1, tzinfo=UTC))
    h = _harness(clock=clock, refresh_ttl=timedelta(days=30))
    client_id = await _register(h.auth)
    first = await _issue_tokens(h, client_id)
    # Advance past the refresh TTL via the pinned clock (no negative timedelta).
    clock.advance(timedelta(days=31))
    with pytest.raises(OAuthError) as exc:
        await h.tokens.exchange(
            TokenRequest(
                grant_type="refresh_token", client_id=client_id, refresh_token=first.refresh_token
            )
        )
    assert exc.value.error == OAuthErrorCode.INVALID_GRANT


# --- revocation (RFC 7009) + connected clients ------------------------------


async def test_revoke_refresh_token_prevents_further_refresh() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    first = await _issue_tokens(h, client_id)
    await h.tokens.revoke(first.refresh_token, client_id=client_id)
    with pytest.raises(OAuthError):
        await h.tokens.exchange(
            TokenRequest(
                grant_type="refresh_token", client_id=client_id, refresh_token=first.refresh_token
            )
        )
    assert any(e.event == OAuthEvent.REVOKED.value for e in h.repo.audit)


async def test_revoke_unknown_or_mismatched_token_is_a_noop() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    first = await _issue_tokens(h, client_id)
    # Unknown token: no error, nothing revoked.
    await h.tokens.revoke("not-a-token", client_id=client_id)
    # Mismatched client: no-op, the token still works.
    await h.tokens.revoke(first.refresh_token, client_id="someone-else")
    rotated = await h.tokens.exchange(
        TokenRequest(
            grant_type="refresh_token", client_id=client_id, refresh_token=first.refresh_token
        )
    )
    assert rotated.refresh_token


async def test_list_connected_clients_reflects_grants() -> None:
    h = _harness()
    client_id = await _register(h.auth, scope="roadmaps:read")
    await _issue_tokens(h, client_id)
    connected = await h.tokens.list_connected_clients(_USER)
    assert len(connected) == 1
    assert connected[0].client_id == client_id
    assert connected[0].client_name == "Test Agent"
    assert connected[0].scopes == ["roadmaps:read"]


async def test_revoke_connected_client_kills_refresh_and_is_scoped_to_owner() -> None:
    h = _harness()
    client_id = await _register(h.auth)
    first = await _issue_tokens(h, client_id)
    await h.tokens.revoke_connected_client(_USER, client_id)
    # The grant's refresh tokens are revoked, so refresh now fails.
    with pytest.raises(OAuthError):
        await h.tokens.exchange(
            TokenRequest(
                grant_type="refresh_token", client_id=client_id, refresh_token=first.refresh_token
            )
        )
    assert await h.tokens.list_connected_clients(_USER) == []
    # Revoking again (or a client the user never authorized) is a 404.
    with pytest.raises(NotFound):
        await h.tokens.revoke_connected_client(_USER, client_id)


async def test_cleanup_stale_clients_drops_old_registrations() -> None:
    clock = MutableClock(datetime(2024, 1, 1, tzinfo=UTC))
    h = _harness(clock=clock)
    client_id = await _register(h.auth)
    # Advance a day, then sweep anything older than an hour: the client qualifies.
    clock.advance(timedelta(days=1))
    deleted = await h.tokens.cleanup_stale_clients(older_than=timedelta(hours=1))
    assert deleted == 1
    assert await h.repo.get_client(client_id) is None


# --- pinned-clock lifecycle + injected counter + N+1 batch ------------------


async def test_pinned_clock_expires_access_but_keeps_refresh_valid() -> None:
    # F5/US-DI-01: mint at t0, advance the pinned clock past the access TTL, and
    # assert "access expired, refresh still valid" -- no sleep, no negative TTL.
    clock = MutableClock(datetime(2024, 1, 1, tzinfo=UTC))
    h = _harness(clock=clock, access_ttl=timedelta(minutes=15), refresh_ttl=timedelta(days=30))
    client_id = await _register(h.auth)
    tokens = await _issue_tokens(h, client_id)
    assert h.codec.verify(tokens.access_token) is not None  # valid at t0

    clock.advance(timedelta(minutes=16))  # past the access TTL, within the refresh TTL

    assert h.codec.verify(tokens.access_token) is None  # access has expired
    rotated = await h.tokens.exchange(
        TokenRequest(
            grant_type="refresh_token", client_id=client_id, refresh_token=tokens.refresh_token
        )
    )
    assert rotated.refresh_token  # refresh still valid -> rotation succeeds
    assert h.codec.verify(rotated.access_token) is not None  # fresh access minted at t0+16m


async def test_issuance_counter_fires_once_post_commit() -> None:
    # F23/US-DI-03: issuance is counted via the injected counter (no business
    # method names the global), exactly once, and only after the commit.
    fired: list[tuple[str, int]] = []
    h = _harness(issued_counter=lambda grant_type: fired.append((grant_type, h.repo.commits)))
    client_id = await _register(h.auth)
    await _issue_tokens(h, client_id)

    assert len(fired) == 1
    grant_type, commits_when_fired = fired[0]
    assert grant_type == "authorization_code"
    # The counter observed the issuance commit already applied (fired post-commit,
    # not before): a pre-commit fire would see one fewer commit than the total.
    assert commits_when_fired == h.repo.commits


async def test_list_connected_clients_skips_a_deleted_client() -> None:
    # F29/US-DI-05: a still-active grant whose client row was deleted is a map
    # miss in the batch read and is skipped rather than surfaced.
    h = _harness()
    kept = await _register(h.auth, scope="roadmaps:read")
    deleted = await _register(h.auth)
    await _issue_tokens(h, kept)
    await _issue_tokens(h, deleted)
    # Delete the client out from under its grant (test-double state manipulation).
    del h.repo._clients[deleted]

    connected = await h.tokens.list_connected_clients(_USER)
    assert [c.client_id for c in connected] == [kept]


async def test_list_connected_clients_issues_one_batch_query() -> None:
    # F29: one batch get_clients read replaces the per-grant serial get_client N+1.
    h = _harness()
    first = await _register(h.auth, scope="roadmaps:read")
    second = await _register(h.auth, scope="roadmaps:write")
    await _issue_tokens(h, first)
    await _issue_tokens(h, second)

    calls = {"get_clients": 0, "get_client": 0}
    original_batch = h.repo.get_clients
    original_single = h.repo.get_client

    async def counting_batch(client_ids: object) -> dict[str, str]:
        calls["get_clients"] += 1
        return await original_batch(client_ids)  # type: ignore[arg-type]

    async def counting_single(client_id: str) -> object:
        calls["get_client"] += 1
        return await original_single(client_id)

    h.repo.get_clients = counting_batch  # type: ignore[method-assign]
    h.repo.get_client = counting_single  # type: ignore[method-assign]

    connected = await h.tokens.list_connected_clients(_USER)
    assert len(connected) == 2
    assert calls == {"get_clients": 1, "get_client": 0}
