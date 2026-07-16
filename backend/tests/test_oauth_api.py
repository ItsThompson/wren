"""HTTP contract tests for the OAuth AS on an external-shaped app.

Drives the whole flow over ``TestClient`` (DCR -> authorize 302 -> consent
context -> decision -> ``/token`` PKCE -> refresh -> revoke) and asserts the wire
contracts: OAuth ``error`` JSON on the protocol endpoints, problem+json on the
SPA endpoints, the Site-URL gotcha (metadata/redirect URLs come from pinned
config, not the request host), CORS for credentialed SPA XHRs, and that no OAuth
route is hidden from the OpenAPI surface.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from tests.conftest import MakeSettings
from tests.oauth_fakes import (
    InMemoryOAuthRepository,
    build_test_codec,
    build_test_config,
    build_test_keyset,
    make_pkce_pair,
)
from wren.api.main import app as external_app
from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.identity import SESSION_COOKIE_NAME, StripInboundIdentityMiddleware
from wren.core.settings import AppSettings
from wren.oauth.api import create_oauth_router
from wren.oauth.authorization import AuthorizationService
from wren.oauth.errors import build_oauth_exception_handlers
from wren.oauth.token_exchange import TokenService

_USER = "user-ada"
_SESSION_COOKIE = "session-ada"
_REDIRECT = "http://127.0.0.1:8765/callback"


class _Fixture:
    def __init__(self, client: TestClient, repo: InMemoryOAuthRepository, codec, config) -> None:
        self.client = client
        self.repo = repo
        self.codec = codec
        self.config = config


def _build_client(make_settings: MakeSettings) -> _Fixture:
    config = build_test_config()
    keyset = build_test_keyset(config)
    codec = build_test_codec(config, keyset)
    repo = InMemoryOAuthRepository()

    def auth_provider() -> AuthorizationService:
        return AuthorizationService(repo, config)

    def token_provider() -> TokenService:
        return TokenService(repo, config, codec)

    router = create_oauth_router(
        config=config,
        keyset=keyset,
        authorization_provider=auth_provider,
        token_provider=token_provider,
    )
    settings: AppSettings = make_settings(cors_origin="https://usewren.com")
    app: FastAPI = create_app(
        settings,
        routers=[router],
        exception_handlers={**build_exception_handlers(), **build_oauth_exception_handlers()},
    )

    async def verify(cookie: str) -> str | None:
        return _USER if cookie == _SESSION_COOKIE else None

    app.state.session_verifier = verify
    app.add_middleware(StripInboundIdentityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.allowed_cors_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return _Fixture(TestClient(app), repo, codec, config)


def _register(client: TestClient) -> str:
    response = client.post(
        "/register", json={"redirect_uris": [_REDIRECT], "client_name": "Test Agent"}
    )
    assert response.status_code == 201, response.text
    return response.json()["client_id"]


def _query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def _authorize(client: TestClient, client_id: str, challenge: str) -> str:
    """Run authorize + approve; return the loopback code."""
    authorize = client.get(
        "/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": _REDIRECT,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
        },
        follow_redirects=False,
    )
    assert authorize.status_code == 302
    auth_request_id = _query(authorize.headers["location"])["auth_request_id"]

    decision = client.post(
        "/authorize/decision",
        json={"auth_request_id": auth_request_id, "approve": True},
        cookies={SESSION_COOKIE_NAME: _SESSION_COOKIE},
    )
    assert decision.status_code == 200, decision.text
    return _query(decision.json()["redirect_uri"])["code"]


# --- discovery + DCR --------------------------------------------------------


def test_as_metadata_urls_come_from_config_not_request_host(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    # Request arrives at "backend:8000" (the cloudflared origin), but the issuer
    # and endpoints must be the pinned public URLs.
    response = fx.client.get(
        "/.well-known/oauth-authorization-server", headers={"host": "backend:8000"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["issuer"] == "https://api.usewren.com"
    assert body["token_endpoint"] == "https://api.usewren.com/token"
    assert body["code_challenge_methods_supported"] == ["S256"]


def test_jwks_endpoint_publishes_public_keys(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    response = fx.client.get("/jwks")
    assert response.status_code == 200
    (key,) = response.json()["keys"]
    assert key["kty"] == "RSA"
    assert "d" not in key


def test_register_mints_a_client_id(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    client_id = _register(fx.client)
    assert client_id


def test_register_bad_redirect_is_oauth_error_json(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    response = fx.client.post("/register", json={"redirect_uris": ["http://evil.example/cb"]})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client_metadata"


def test_register_empty_redirect_uris_is_rejected_at_dcr(make_settings: MakeSettings) -> None:
    # The schema's min_length=1 rejects an empty redirect_uris list at the DCR
    # boundary (RFC 9457 problem+json) before the service validation loop.
    fx = _build_client(make_settings)
    response = fx.client.post("/register", json={"redirect_uris": []})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


# --- authorize 302 + Site-URL gotcha ----------------------------------------


def test_authorize_redirects_to_the_spa_consent_url(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    client_id = _register(fx.client)
    _verifier, challenge = make_pkce_pair()
    response = fx.client.get(
        "/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": _REDIRECT,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        headers={"host": "backend:8000"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    # The consent URL is the pinned SPA origin, never the request host.
    assert response.headers["location"].startswith("https://usewren.com/authorize?")


def test_authorize_invalid_request_is_oauth_error_json(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    client_id = _register(fx.client)
    # Missing PKCE -> invalid_request in OAuth JSON, not problem+json.
    response = fx.client.get(
        "/authorize",
        params={"client_id": client_id, "redirect_uri": _REDIRECT, "response_type": "code"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


# --- consent context + decision auth ----------------------------------------


def test_context_reports_authenticated_flag(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    client_id = _register(fx.client)
    _verifier, challenge = make_pkce_pair()
    location = fx.client.get(
        "/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": _REDIRECT,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    ).headers["location"]
    auth_request_id = _query(location)["auth_request_id"]

    anon = fx.client.get("/authorize/context", params={"auth_request_id": auth_request_id})
    assert anon.status_code == 200
    assert anon.json()["authenticated"] is False
    assert anon.json()["client_name"] == "Test Agent"

    signed_in = fx.client.get(
        "/authorize/context",
        params={"auth_request_id": auth_request_id},
        cookies={SESSION_COOKIE_NAME: _SESSION_COOKIE},
    )
    assert signed_in.json()["authenticated"] is True


def test_decision_without_a_session_is_401_problem_json(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    response = fx.client.post(
        "/authorize/decision", json={"auth_request_id": "whatever", "approve": True}
    )
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "UNAUTHORIZED"


def test_expired_or_missing_context_is_404_problem_json(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    response = fx.client.get("/authorize/context", params={"auth_request_id": "nope"})
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


# --- token endpoint (form-encoded) ------------------------------------------


def test_full_pkce_flow_issues_an_audience_bound_token(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    client_id = _register(fx.client)
    verifier, challenge = make_pkce_pair()
    code = _authorize(fx.client, client_id, challenge)

    response = fx.client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": _REDIRECT,
        },
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["token_type"] == "Bearer"
    verified = fx.codec.verify(body["access_token"])
    assert verified is not None
    assert verified.subject == _USER
    assert verified.audience == fx.config.resource

    # The rotating refresh token exchanges for a fresh pair.
    refreshed = fx.client.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": body["refresh_token"],
        },
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != body["refresh_token"]


def test_token_pkce_mismatch_is_oauth_error_json(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    client_id = _register(fx.client)
    _verifier, challenge = make_pkce_pair()
    code = _authorize(fx.client, client_id, challenge)
    response = fx.client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": "wrong",
            "redirect_uri": _REDIRECT,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


def test_revoke_then_refresh_fails(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    client_id = _register(fx.client)
    verifier, challenge = make_pkce_pair()
    code = _authorize(fx.client, client_id, challenge)
    tokens = fx.client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": _REDIRECT,
        },
    ).json()

    revoke = fx.client.post(
        "/revoke", data={"token": tokens["refresh_token"], "client_id": client_id}
    )
    assert revoke.status_code == 200

    refreshed = fx.client.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": tokens["refresh_token"],
        },
    )
    assert refreshed.status_code == 400
    assert refreshed.json()["error"] == "invalid_grant"


# --- connected clients ------------------------------------------------------


def test_me_clients_requires_a_session(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    assert fx.client.get("/me/clients").status_code == 401


def test_me_clients_lists_and_revokes_own_clients(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    client_id = _register(fx.client)
    verifier, challenge = make_pkce_pair()
    code = _authorize(fx.client, client_id, challenge)
    fx.client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": _REDIRECT,
        },
    )
    listed = fx.client.get("/me/clients", cookies={SESSION_COOKIE_NAME: _SESSION_COOKIE})
    assert listed.status_code == 200
    assert [c["client_id"] for c in listed.json()] == [client_id]

    revoked = fx.client.delete(
        f"/me/clients/{client_id}", cookies={SESSION_COOKIE_NAME: _SESSION_COOKIE}
    )
    assert revoked.status_code == 204
    assert fx.client.get("/me/clients", cookies={SESSION_COOKIE_NAME: _SESSION_COOKIE}).json() == []


# --- CORS + OpenAPI surface -------------------------------------------------


def test_cors_allows_the_configured_origin_with_credentials(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    response = fx.client.get("/jwks", headers={"origin": "https://usewren.com"})
    assert response.headers["access-control-allow-origin"] == "https://usewren.com"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_preflight_is_answered(make_settings: MakeSettings) -> None:
    fx = _build_client(make_settings)
    response = fx.client.options(
        "/authorize/context",
        headers={
            "origin": "https://usewren.com",
            "access-control-request-method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://usewren.com"


@pytest.mark.parametrize(
    "path",
    [
        "/.well-known/oauth-authorization-server",
        "/jwks",
        "/register",
        "/authorize",
        "/authorize/context",
        "/authorize/decision",
        "/token",
        "/revoke",
        "/me/clients",
        "/me/clients/{client_id}",
    ],
)
def test_oauth_routes_are_not_hidden_from_openapi(path: str) -> None:
    # The route-coverage net enumerates via app.openapi(); a route hidden with
    # include_in_schema=False would silently escape access-level coverage.
    assert path in external_app.openapi()["paths"]
