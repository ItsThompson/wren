"""Contract tests for the /roadmaps surface on an external-shaped app.

Asserts the RFC 9457 problem+json shapes, that create returns 201 with a minted
roadmap_id + slug IDs, that owner-scoped reads return 200 to the owner and 404 to
a non-owner (no existence leak), that require_user gates the surface (401
anonymous, spoofed X-User-ID stripped), and that malformed input is a 422 in the
one error contract. The service is backed by the in-memory repository; no
database is required.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from accounts_fakes import InMemoryAccountRepository, build_test_codec, build_test_hasher
from roadmaps_fakes import InMemoryRoadmapRepository, sequence_token_factory
from wren.accounts.api import create_accounts_router
from wren.accounts.config import CookieConfig
from wren.accounts.service import AccountService
from wren.accounts.session import create_session_verifier
from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.identity import USER_ID_HEADER, StripInboundIdentityMiddleware
from wren.core.settings import AppSettings
from wren.roadmaps.api import create_roadmaps_router
from wren.roadmaps.service import RoadmapService

MakeSettings = Callable[..., AppSettings]

_PASSWORD = "Str0ngPass"

_MINIMAL_ROADMAP = {
    "title": "Grokking DSA",
    "sections": [
        {
            "title": "Foundations",
            "subsections": [
                {
                    "title": "Arrays",
                    "resources": [{"title": "Guide", "url": "https://x.test", "type": "article"}],
                    "checklist_items": [{"text": "Read it"}],
                }
            ],
        }
    ],
}


def _build_client(
    make_settings: MakeSettings, *, tokens: list[str] | None = None
) -> tuple[TestClient, InMemoryRoadmapRepository]:
    """An external-shaped app with the /auth + /roadmaps routers over in-memory
    repositories and the real session verifier (so login sets a resolvable
    cookie)."""
    account_repo = InMemoryAccountRepository()
    codec = build_test_codec()
    hasher = build_test_hasher()
    roadmap_repo = InMemoryRoadmapRepository()

    def account_provider() -> AccountService:
        return AccountService(account_repo, hasher, codec)

    def roadmap_provider() -> RoadmapService:
        return RoadmapService(
            roadmap_repo,
            token_factory=sequence_token_factory(tokens or ["7f3k", "9x2b", "abcd", "efgh"]),
        )

    accounts_router = create_accounts_router(
        account_provider, cookie_config=CookieConfig(secure=False, domain=None)
    )
    roadmaps_router = create_roadmaps_router(roadmap_provider)

    app: FastAPI = create_app(
        make_settings(),
        routers=[accounts_router, roadmaps_router],
        exception_handlers=build_exception_handlers(),
    )
    app.state.session_verifier = create_session_verifier(codec, account_repo.is_session_revoked)
    app.add_middleware(StripInboundIdentityMiddleware)
    return TestClient(app), roadmap_repo


def _login(client: TestClient, username: str = "ada", email: str = "ada@example.com") -> None:
    response = client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": _PASSWORD},
    )
    assert response.status_code == 201, response.text


# --- create -----------------------------------------------------------------


def test_create_returns_201_with_a_minted_roadmap_id(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    response = client.post("/roadmaps", json=_MINIMAL_ROADMAP)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] == "grokking-dsa-7f3k"
    assert body["status"] == "draft"
    assert body["revision"] == 1
    assert body["visibility"] == "private"


def test_create_mints_prefixed_slug_ids_for_every_node(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    body = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()
    section = body["sections"]["sec_foundations"]
    subsection = section["subsections"]["sub_arrays"]
    assert section["subsection_order"] == ["sub_arrays"]
    assert subsection["resource_order"][0].startswith("res_")
    assert subsection["item_order"][0].startswith("chk_")
    # remap is present (empty here: nothing was de-duped).
    assert body["remap"] == {}


def test_create_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post("/roadmaps", json=_MINIMAL_ROADMAP)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_create_malformed_body_is_a_422_problem_json(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    # Missing the required "title".
    response = client.post("/roadmaps", json={"sections": []})
    assert response.status_code == 422
    body = response.json()
    assert response.headers["content-type"] == "application/problem+json"
    assert body["code"] == "VALIDATION"
    assert any("title" in field for field in body["fields"])


# --- get: owner-scoped, no existence leak -----------------------------------


def test_get_returns_the_full_roadmap_to_its_owner(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]

    response = client.get(f"/roadmaps/{created_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created_id
    assert "sec_foundations" in body["sections"]


def test_get_is_404_to_a_non_owner_without_leaking_existence(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client, username="owner", email="owner@example.com")
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]

    # Switch to a different user session.
    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    response = client.get(f"/roadmaps/{created_id}")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_get_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.get("/roadmaps/anything-0000")
    assert response.status_code == 401


def test_get_ignores_a_spoofed_x_user_id_header(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client, username="owner", email="owner@example.com")
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]

    # A second user cannot reach the draft even by spoofing the owner's id: the
    # header is stripped and identity comes from the cookie.
    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    response = client.get(f"/roadmaps/{created_id}", headers={USER_ID_HEADER: "owner"})
    assert response.status_code == 404
