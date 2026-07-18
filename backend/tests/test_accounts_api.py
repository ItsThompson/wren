"""Contract tests for the /auth surface on an external-shaped app.

Asserts RFC 9457 problem+json error shapes, session-cookie attributes, that
require_user resolves the cookie to the right user (per-user scoping) with any
spoofed X-User-ID stripped, and the login/refresh/logout/revocation flow.
The service is backed by the in-memory repository; no database is required.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.support.fakes.accounts_fakes import (
    InMemoryAccountRepository,
    build_test_codec,
    build_test_hasher,
)
from wren.accounts.api import create_accounts_router
from wren.accounts.config import REFRESH_COOKIE_NAME, CookieConfig
from wren.accounts.notifications import DiscordRegistrationNotifier
from wren.accounts.service import AccountService
from wren.accounts.session import create_session_verifier
from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.identity import (
    SESSION_COOKIE_NAME,
    USER_ID_HEADER,
    StripInboundIdentityMiddleware,
    require_user,
)
from wren.core.settings import AppSettings

if TYPE_CHECKING:
    from wren.accounts.tokens import SessionTokenCodec

MakeSettings = Callable[..., AppSettings]

_PASSWORD = "Str0ngPass"


def _build_client(
    make_settings: MakeSettings,
    *,
    cookie_config: CookieConfig | None = None,
    codec: SessionTokenCodec | None = None,
) -> tuple[TestClient, InMemoryAccountRepository]:
    repo = InMemoryAccountRepository()
    codec = codec or build_test_codec()
    hasher = build_test_hasher()

    def provider() -> AccountService:
        return AccountService(repo, hasher, codec)

    accounts_router = create_accounts_router(
        provider, cookie_config=cookie_config or CookieConfig(secure=False, domain=None)
    )

    # A protected route to observe what require_user resolves and whether a
    # spoofed X-User-ID survived to the handler.
    protected = APIRouter()

    @protected.get("/me/whoami")
    async def whoami(
        request: Request, user_id: str = Depends(require_user)
    ) -> dict[str, str | None]:
        return {"user_id": user_id, "seen_x_user_id": request.headers.get(USER_ID_HEADER)}

    app: FastAPI = create_app(
        make_settings(),
        routers=[accounts_router, protected],
        exception_handlers=build_exception_handlers(),
    )
    app.state.session_verifier = create_session_verifier(codec, repo.is_session_revoked)
    app.add_middleware(StripInboundIdentityMiddleware)
    return TestClient(app), repo


def _register(client: TestClient, username: str = "ada", email: str = "ada@example.com") -> None:
    response = client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": _PASSWORD},
    )
    assert response.status_code == 201, response.text


# --- register ---------------------------------------------------------------


def test_register_returns_the_user_without_password_material(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post(
        "/auth/register",
        json={"username": "ada", "email": "Ada@Example.com", "password": _PASSWORD},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "ada"
    assert body["email"] == "ada@example.com"
    assert "password" not in body and "password_hash" not in body


def test_register_sets_httponly_samesite_session_cookies(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post(
        "/auth/register",
        json={"username": "ada", "email": "ada@example.com", "password": _PASSWORD},
    )
    set_cookies = "\n".join(response.headers.get_list("set-cookie"))
    assert SESSION_COOKIE_NAME in set_cookies
    assert REFRESH_COOKIE_NAME in set_cookies
    assert "httponly" in set_cookies.lower()
    assert "samesite=lax" in set_cookies.lower()


def test_prod_cookie_config_is_secure_and_domain_scoped(make_settings: MakeSettings) -> None:
    client, _ = _build_client(
        make_settings, cookie_config=CookieConfig(secure=True, domain=".usewren.com")
    )
    response = client.post(
        "/auth/register",
        json={"username": "ada", "email": "ada@example.com", "password": _PASSWORD},
    )
    set_cookies = "\n".join(response.headers.get_list("set-cookie")).lower()
    assert "secure" in set_cookies
    assert "domain=.usewren.com" in set_cookies


def test_duplicate_email_is_a_field_level_problem_json(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _register(client)
    response = client.post(
        "/auth/register",
        json={"username": "adalove", "email": "ada@example.com", "password": _PASSWORD},
    )
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "CONFLICT"
    assert body["fields"]["email"]


def test_duplicate_username_is_a_field_level_problem_json(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _register(client)
    response = client.post(
        "/auth/register",
        json={"username": "ada", "email": "other@example.com", "password": _PASSWORD},
    )
    assert response.status_code == 409
    assert response.json()["fields"]["username"]


def test_weak_password_is_a_422_problem_json_with_the_field(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post(
        "/auth/register",
        json={"username": "ada", "email": "ada@example.com", "password": "weak"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION"
    assert body["fields"]["password"]


def test_malformed_email_uses_the_same_problem_json_contract(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post(
        "/auth/register",
        json={"username": "ada", "email": "not-an-email", "password": _PASSWORD},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION"
    # RequestValidationError is mapped into the same field-map shape.
    assert any("email" in field for field in body["fields"])


async def test_register_makes_exactly_one_discord_post_and_returns_201(
    make_settings: MakeSettings,
) -> None:
    # S3: exercise the REAL POST path end-to-end (not just the spy) via an
    # ASGITransport client so the fire-and-forget task and the aclose() drain
    # share one event loop. Assert 201 AND exactly one transport hit.
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    notifier = DiscordRegistrationNotifier(
        SecretStr("https://discord.test/webhooks/123/secret"),
        transport=httpx.MockTransport(handler),
    )
    repo = InMemoryAccountRepository()

    def provider() -> AccountService:
        return AccountService(repo, build_test_hasher(), build_test_codec(), notifier=notifier)

    accounts_router = create_accounts_router(
        provider, cookie_config=CookieConfig(secure=False, domain=None)
    )
    app: FastAPI = create_app(
        make_settings(), routers=[accounts_router], exception_handlers=build_exception_handlers()
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/auth/register",
            json={"username": "ada", "email": "ada@example.com", "password": _PASSWORD},
        )
    await notifier.aclose()  # drain the scheduled delivery before asserting

    assert response.status_code == 201, response.text
    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert json.loads(seen[0].content) == {"content": "🎉 New user registered: ada"}


# --- login / require_user resolution ----------------------------------------


def test_login_then_require_user_resolves_the_cookie_owner(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _register(client)
    client.cookies.clear()

    login = client.post("/auth/login", json={"email": "ada@example.com", "password": _PASSWORD})
    assert login.status_code == 200
    user_id = login.json()["id"]

    whoami = client.get("/me/whoami")
    assert whoami.status_code == 200
    assert whoami.json()["user_id"] == user_id


def test_require_user_uses_the_cookie_and_strips_spoofed_header(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings)
    _register(client)
    user_id = client.post(
        "/auth/login", json={"email": "ada@example.com", "password": _PASSWORD}
    ).json()["id"]

    whoami = client.get("/me/whoami", headers={USER_ID_HEADER: "attacker"})
    assert whoami.status_code == 200
    body = whoami.json()
    # Identity is the cookie owner; the spoofed header never reached the handler.
    assert body["user_id"] == user_id
    assert body["seen_x_user_id"] is None


def test_each_session_resolves_to_its_own_user(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _register(client, username="ada", email="ada@example.com")
    ada_id = client.get("/me/whoami").json()["user_id"]

    client.cookies.clear()
    _register(client, username="bob", email="bob@example.com")
    bob_id = client.get("/me/whoami").json()["user_id"]

    assert ada_id != bob_id


def test_whoami_without_a_cookie_is_401(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.get("/me/whoami")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize(
    ("email", "password"),
    [("ada@example.com", "WrongPass9"), ("ghost@example.com", "Str0ngPass")],
)
def test_bad_credentials_are_a_generic_401(
    make_settings: MakeSettings, email: str, password: str
) -> None:
    client, _ = _build_client(make_settings)
    _register(client)
    client.cookies.clear()
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    # Same detail whether the email exists or not: no account-existence leak.
    assert response.json()["detail"] == "Invalid email or password."


# --- refresh / logout / revocation ------------------------------------------


def test_refresh_rotates_the_session_and_keeps_the_user(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _register(client)
    user_id = client.get("/me/whoami").json()["user_id"]

    refreshed = client.post("/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["id"] == user_id
    # The new access cookie still resolves the same user.
    assert client.get("/me/whoami").json()["user_id"] == user_id


def test_refresh_without_a_refresh_cookie_is_401(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post("/auth/refresh")
    assert response.status_code == 401


def test_logout_clears_cookies_and_revokes_the_session(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _register(client)
    # Capture the live access token before logout so we can prove revocation.
    access_before = client.cookies.get(SESSION_COOKIE_NAME)
    assert access_before is not None

    logout = client.post("/auth/logout")
    assert logout.status_code == 204

    # Re-presenting the pre-logout access token is rejected: logout blacklisted
    # its session id, so the still-unexpired access token no longer resolves.
    client.cookies.clear()
    response = client.get("/me/whoami", cookies={SESSION_COOKIE_NAME: access_before})
    assert response.status_code == 401


def test_a_revoked_refresh_cannot_mint_a_new_access_token(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _register(client)
    refresh_before = client.cookies.get(REFRESH_COOKIE_NAME)
    assert refresh_before is not None

    client.post("/auth/logout")

    client.cookies.clear()
    response = client.post("/auth/refresh", cookies={REFRESH_COOKIE_NAME: refresh_before})
    assert response.status_code == 401
