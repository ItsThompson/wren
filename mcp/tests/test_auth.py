"""Auth-boundary tests: 401 + WWW-Authenticate, pass-through, and identity plumbing.

Exercises the real :class:`BearerAuthMiddleware` over a FastAPI app with a real
verifier (faked JWKS): an unauthenticated request to the guarded prefix gets a
401 pointing at the PRM (RFC 9728), a valid bearer passes and resolves the
principal for the handler, and unguarded paths are untouched.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from token_factory import ISSUER, RESOURCE, make_fetch, mint, new_key, public_jwks
from wren_mcp.auth import BearerAuthMiddleware, _extract_bearer, agent_identity
from wren_mcp.config import MCP_PATH, PRM_PATH
from wren_mcp.keys import RemoteKeyProvider
from wren_mcp.tokens import AgentTokenVerifier, VerifiedAgentToken


def _build_app(key) -> FastAPI:
    fetch = make_fetch(public_jwks(key))
    verifier = AgentTokenVerifier(
        RemoteKeyProvider(ISSUER, fetch), issuer=ISSUER, resource=RESOURCE
    )
    app = FastAPI()
    router = APIRouter()

    @router.get("/mcp/ping")
    async def ping(agent: VerifiedAgentToken = Depends(agent_identity)) -> dict[str, str]:
        return {"user_id": agent.user_id, "scope": agent.scope}

    @router.get("/open")
    async def open_endpoint() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/leaky")
    async def leaky(agent: VerifiedAgentToken = Depends(agent_identity)) -> dict[str, str]:
        # A route that uses agent_identity but is mounted OUTSIDE the guarded
        # prefix: the middleware never sets identity, so it must fail closed.
        return {"user_id": agent.user_id}

    app.include_router(router)
    app.add_middleware(
        BearerAuthMiddleware, verifier=verifier, resource=RESOURCE, protected_prefix=MCP_PATH
    )
    return app


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_unauthenticated_call_to_the_guarded_prefix_is_401_with_challenge() -> None:
    client = TestClient(_build_app(new_key()))

    response = client.get("/mcp/ping")

    assert response.status_code == 401
    challenge = response.headers["WWW-Authenticate"]
    assert challenge == f'Bearer resource_metadata="{RESOURCE}{PRM_PATH}"'
    assert response.json()["error"] == "invalid_token"


def test_invalid_bearer_is_401_with_challenge() -> None:
    client = TestClient(_build_app(new_key()))

    response = client.get("/mcp/ping", headers=_bearer("garbage.token.value"))

    assert response.status_code == 401
    assert "resource_metadata" in response.headers["WWW-Authenticate"]


def test_wrong_audience_bearer_is_401() -> None:
    key = new_key()
    client = TestClient(_build_app(key))

    response = client.get("/mcp/ping", headers=_bearer(mint(key, aud="https://other.example")))

    assert response.status_code == 401


def test_valid_bearer_passes_and_resolves_the_principal() -> None:
    key = new_key()
    client = TestClient(_build_app(key))

    response = client.get(
        "/mcp/ping", headers=_bearer(mint(key, sub="user-ada", scope="roadmaps:read"))
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": "user-ada", "scope": "roadmaps:read"}


def test_unguarded_paths_are_not_authenticated() -> None:
    client = TestClient(_build_app(new_key()))

    response = client.get("/open")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_agent_identity_fails_closed_outside_the_guarded_prefix() -> None:
    key = new_key()
    client = TestClient(_build_app(key))

    # Even with a valid token, /leaky is not under the guarded prefix, so the
    # middleware never set the principal: the dependency fails closed.
    response = client.get("/leaky", headers=_bearer(mint(key)))

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("", None),
        ("Bearer ", None),
        ("Basic abc", None),
        ("Bearer   ", None),
        ("Bearer abc.def.ghi", "abc.def.ghi"),
    ],
)
def test_extract_bearer(header: str | None, expected: str | None) -> None:
    assert _extract_bearer(header) == expected
