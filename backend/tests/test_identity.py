"""Identity dependencies: external strips X-User-ID and resolves the cookie;
internal trusts X-User-ID behind the shared INTERNAL_API_TOKEN. The strip-vs-trust
behavior is asserted on an external-shaped app and an internal-shaped app."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.testclient import TestClient

from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.identity import (
    INTERNAL_TOKEN_HEADER,
    SESSION_COOKIE_NAME,
    USER_ID_HEADER,
    SessionVerifier,
    StripInboundIdentityMiddleware,
    deny_all_sessions,
    require_internal_user,
    require_user,
)
from wren.core.settings import AppSettings

MakeSettings = Callable[..., AppSettings]

_VALID_COOKIE = "valid-cookie"
_COOKIE_USER = "user-from-cookie"
_INTERNAL_TOKEN = "s3cret-internal-token"


def _cookie_verifier(cookie: str) -> str | None:
    return _COOKIE_USER if cookie == _VALID_COOKIE else None


async def _async_cookie_verifier(cookie: str) -> str | None:
    return _cookie_verifier(cookie)


def _external_client(
    make_settings: MakeSettings,
    *,
    verifier: SessionVerifier | None = _async_cookie_verifier,
) -> TestClient:
    router = APIRouter()

    @router.get("/whoami")
    async def whoami(
        request: Request, user_id: str = Depends(require_user)
    ) -> dict[str, str | None]:
        # Reveals whether a client-supplied X-User-ID survived to the handler.
        return {"user_id": user_id, "seen_x_user_id": request.headers.get(USER_ID_HEADER)}

    app: FastAPI = create_app(
        make_settings(),
        routers=[router],
        exception_handlers=build_exception_handlers(),
    )
    if verifier is not None:
        app.state.session_verifier = verifier
    app.add_middleware(StripInboundIdentityMiddleware)
    return TestClient(app)


def _internal_client(make_settings: MakeSettings, *, token: str = _INTERNAL_TOKEN) -> TestClient:
    router = APIRouter()

    @router.get("/whoami")
    async def whoami(user_id: str = Depends(require_internal_user)) -> dict[str, str]:
        return {"user_id": user_id}

    app: FastAPI = create_app(
        make_settings(),
        routers=[router],
        exception_handlers=build_exception_handlers(),
    )
    app.state.internal_api_token = token
    return TestClient(app)


# --- external app: cookie resolution + X-User-ID strip ----------------------


def test_external_resolves_user_from_session_cookie(make_settings: MakeSettings) -> None:
    response = _external_client(make_settings).get(
        "/whoami", headers={"Cookie": f"{SESSION_COOKIE_NAME}={_VALID_COOKIE}"}
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == _COOKIE_USER


def test_external_strips_spoofed_x_user_id_and_uses_the_cookie(make_settings: MakeSettings) -> None:
    response = _external_client(make_settings).get(
        "/whoami",
        headers={
            "Cookie": f"{SESSION_COOKIE_NAME}={_VALID_COOKIE}",
            USER_ID_HEADER: "attacker",
        },
    )
    assert response.status_code == 200
    body = response.json()
    # Identity is the cookie's user; the spoofed header never reached the handler.
    assert body["user_id"] == _COOKIE_USER
    assert body["seen_x_user_id"] is None


def test_external_401_without_a_cookie(make_settings: MakeSettings) -> None:
    response = _external_client(make_settings).get("/whoami")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_external_401_for_an_invalid_cookie(make_settings: MakeSettings) -> None:
    response = _external_client(make_settings).get(
        "/whoami", headers={"Cookie": f"{SESSION_COOKIE_NAME}=bogus"}
    )
    assert response.status_code == 401


def test_external_default_verifier_denies_all_sessions(make_settings: MakeSettings) -> None:
    # With no verifier injected, the app falls back to deny_all_sessions (the
    # default deny-all verifier), so even a "valid"-looking cookie is denied.
    client = _external_client(make_settings, verifier=None)
    response = client.get("/whoami", headers={"Cookie": f"{SESSION_COOKIE_NAME}={_VALID_COOKIE}"})
    assert response.status_code == 401


async def test_deny_all_sessions_returns_none() -> None:
    assert await deny_all_sessions("anything") is None


async def test_strip_middleware_passes_non_http_scopes_through_untouched() -> None:
    # Lifespan/websocket scopes must reach the inner app unmodified; only http
    # request headers are filtered.
    seen: dict[str, object] = {}

    async def inner(scope: object, receive: object, send: object) -> None:
        seen["scope"] = scope

    middleware = StripInboundIdentityMiddleware(inner)  # type: ignore[arg-type]
    scope = {"type": "lifespan"}

    async def receive() -> dict[str, str]:
        return {}

    async def send(_message: object) -> None:
        return None

    await middleware(scope, receive, send)  # type: ignore[arg-type]
    assert seen["scope"] is scope


# --- internal app: trusted X-User-ID behind the shared token ----------------


def test_internal_trusts_x_user_id_with_a_valid_token(make_settings: MakeSettings) -> None:
    response = _internal_client(make_settings).get(
        "/whoami",
        headers={INTERNAL_TOKEN_HEADER: _INTERNAL_TOKEN, USER_ID_HEADER: "agent-user"},
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == "agent-user"


def test_internal_401_when_token_missing(make_settings: MakeSettings) -> None:
    response = _internal_client(make_settings).get(
        "/whoami", headers={USER_ID_HEADER: "agent-user"}
    )
    assert response.status_code == 401


def test_internal_401_for_a_wrong_token(make_settings: MakeSettings) -> None:
    response = _internal_client(make_settings).get(
        "/whoami",
        headers={INTERNAL_TOKEN_HEADER: "wrong", USER_ID_HEADER: "agent-user"},
    )
    assert response.status_code == 401


def test_internal_401_for_a_non_ascii_token(make_settings: MakeSettings) -> None:
    # A non-ASCII token must deny cleanly (401), not crash secrets.compare_digest
    # with a TypeError surfacing as a 500. Sent as raw latin-1 bytes so Starlette
    # decodes it to a non-ASCII str server-side (httpx blocks non-ASCII str values).
    response = _internal_client(make_settings).get(
        "/whoami",
        headers={INTERNAL_TOKEN_HEADER: b"t\xf6k\xe9n", USER_ID_HEADER: "agent-user"},
    )
    assert response.status_code == 401


def test_internal_401_when_x_user_id_missing(make_settings: MakeSettings) -> None:
    response = _internal_client(make_settings).get(
        "/whoami", headers={INTERNAL_TOKEN_HEADER: _INTERNAL_TOKEN}
    )
    assert response.status_code == 401


def test_internal_unconfigured_token_denies_all(make_settings: MakeSettings) -> None:
    # A blank expected token fail-safe denies rather than matching a blank header.
    client = _internal_client(make_settings, token="")
    response = client.get(
        "/whoami", headers={INTERNAL_TOKEN_HEADER: "", USER_ID_HEADER: "agent-user"}
    )
    assert response.status_code == 401
