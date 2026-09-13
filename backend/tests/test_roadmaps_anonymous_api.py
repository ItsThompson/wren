"""Anonymous full-document access and protected-route contract tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from tests.support.fakes.accounts_fakes import (
    InMemoryAccountRepository,
    build_test_codec,
    build_test_hasher,
)
from tests.support.fakes.progress_fakes import InMemoryProgressRepository
from tests.support.fakes.roadmaps_fakes import (
    InMemoryRoadmapRepository,
    sequence_token_factory,
)
from wren.accounts.api import create_accounts_router
from wren.accounts.config import CookieConfig
from wren.accounts.service import AccountService
from wren.accounts.session import create_session_verifier
from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.identity import StripInboundIdentityMiddleware
from wren.core.route_registry import App
from wren.core.settings import AppSettings
from wren.progress.router import create_progress_router
from wren.progress.service import ProgressService
from wren.roadmaps.listing import ListingService, ProfileOwner
from wren.roadmaps.listing_api import create_listing_router
from wren.roadmaps.read_service import RoadmapReadService
from wren.roadmaps.router import create_roadmaps_router
from wren.roadmaps.service import RoadmapService

if TYPE_CHECKING:
    from fastapi import FastAPI

MakeSettings = Callable[..., AppSettings]
_PASSWORD = "Str0ngPass"
_OWNER = "owner"

_COMPLETE_ROADMAP = {
    "title": "Grokking DSA",
    "description": "A complete prerequisite-aware path.",
    "subject_tags": ["computer-science", "interview-prep"],
    "suggested_path": ["sub_arrays", "sub_hashing"],
    "sections": [
        {
            "title": "Foundations",
            "subsections": [
                {
                    "proposed_id": "sub_arrays",
                    "title": "Arrays",
                    "description": "Start with arrays.",
                    "tags": ["arrays"],
                    "effort_estimate": "2h",
                    "resources": [
                        {
                            "proposed_id": "res_guide",
                            "title": "Guide",
                            "url": "https://x.test/guide",
                            "type": "article",
                        }
                    ],
                    "checklist_items": [{"proposed_id": "chk_read", "text": "Read the guide"}],
                },
                {
                    "proposed_id": "sub_hashing",
                    "title": "Hashing",
                    "tags": ["hashing"],
                    "prereq_ids": ["sub_arrays"],
                    "resources": [
                        {
                            "proposed_id": "res_video",
                            "title": "Video",
                            "url": "https://x.test/video",
                            "type": "video",
                        }
                    ],
                    "checklist_items": [{"proposed_id": "chk_hash", "text": "Implement a counter"}],
                },
            ],
        }
    ],
}


def _build_client(
    make_settings: MakeSettings,
) -> tuple[TestClient, InMemoryRoadmapRepository, InMemoryProgressRepository]:
    account_repo = InMemoryAccountRepository()
    codec = build_test_codec()
    roadmap_repo = InMemoryRoadmapRepository()
    progress_repo = InMemoryProgressRepository()

    def account_provider() -> AccountService:
        return AccountService(account_repo, build_test_hasher(), codec)

    def roadmap_provider() -> RoadmapService:
        return RoadmapService(
            roadmap_repo,
            follower_counter=progress_repo.count_followers,
            token_factory=sequence_token_factory(["7f3k", "9x2b", "abcd"]),
        )

    def read_provider() -> RoadmapReadService:
        return RoadmapReadService(roadmap_repo)

    def progress_provider() -> ProgressService:
        return ProgressService(roadmap_repo, progress_repo)

    async def resolve_handle(_handle: str) -> ProfileOwner | None:
        return None

    def listing_provider() -> ListingService:
        return ListingService(
            roadmap_repo,
            handle_resolver=resolve_handle,
            followed_reader=progress_repo.list_followed_roadmap_ids,
        )

    app: FastAPI = create_app(
        make_settings(),
        routers=[
            create_accounts_router(
                account_provider, cookie_config=CookieConfig(secure=False, domain=None)
            ),
            create_roadmaps_router(roadmap_provider, read_provider, app=App.EXTERNAL),
            create_progress_router(progress_provider, app=App.EXTERNAL),
            create_listing_router(listing_provider, app=App.EXTERNAL),
        ],
        exception_handlers=build_exception_handlers(),
    )
    app.state.session_verifier = create_session_verifier(codec, account_repo.is_session_revoked)
    app.add_middleware(StripInboundIdentityMiddleware)
    return TestClient(app), roadmap_repo, progress_repo


def _login(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"username": _OWNER, "email": "owner@example.com", "password": _PASSWORD},
    )
    assert response.status_code == 201, response.text


def _create_published_public(client: TestClient) -> str:
    body = client.post("/roadmaps", json=_COMPLETE_ROADMAP).json()
    assert isinstance(body, dict)
    roadmap_id = body["id"]
    assert isinstance(roadmap_id, str)
    assert client.post(f"/roadmaps/{roadmap_id}:publish").status_code == 200
    assert (
        client.put(f"/roadmaps/{roadmap_id}/visibility", json={"visibility": "public"}).status_code
        == 200
    )
    return roadmap_id


def test_cookie_free_public_document_preserves_complete_contract(
    make_settings: MakeSettings,
) -> None:
    client, _, progress_repo = _build_client(make_settings)
    _login(client)
    roadmap_id = _create_published_public(client)

    client.cookies.clear()
    response = client.get(f"/roadmaps/{roadmap_id}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["title"] == _COMPLETE_ROADMAP["title"]
    assert body["description"] == _COMPLETE_ROADMAP["description"]
    assert body["subject_tags"] == _COMPLETE_ROADMAP["subject_tags"]
    assert body["section_order"] == ["sec_foundations"]
    assert body["suggested_path"] == ["sub_arrays", "sub_hashing"]
    section = body["sections"]["sec_foundations"]
    assert section["subsection_order"] == ["sub_arrays", "sub_hashing"]
    arrays = section["subsections"]["sub_arrays"]
    hashing = section["subsections"]["sub_hashing"]
    assert arrays["description"] == "Start with arrays."
    assert arrays["tags"] == ["arrays"]
    assert arrays["resource_order"] == ["res_guide"]
    assert arrays["resources"]["res_guide"]["url"] == "https://x.test/guide"
    assert arrays["item_order"] == ["chk_read"]
    assert arrays["checklist_items"]["chk_read"]["text"] == "Read the guide"
    assert hashing["prereq_ids"] == ["sub_arrays"]
    assert progress_repo._by_key == {}


def test_cookie_free_public_archived_document_is_readable(
    make_settings: MakeSettings,
) -> None:
    client, _, progress_repo = _build_client(make_settings)
    _login(client)
    roadmap_id = _create_published_public(client)
    assert client.post(f"/roadmaps/{roadmap_id}:archive").status_code == 200

    client.cookies.clear()
    response = client.get(f"/roadmaps/{roadmap_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "archived"
    assert progress_repo._by_key == {}


@pytest.mark.parametrize("path", ["/roadmaps/unknown-0000", "/roadmaps/unknown-0000/progress"])
def test_cookie_free_denial_does_not_disclose_private_or_unknown_resources(
    path: str, make_settings: MakeSettings
) -> None:
    client, _, _ = _build_client(make_settings)
    response = client.get(path)
    assert response.status_code == (401 if path.endswith("progress") else 404)
    assert response.json()["code"] == ("UNAUTHORIZED" if path.endswith("progress") else "NOT_FOUND")


def test_cookie_free_private_and_public_draft_reads_are_404(
    make_settings: MakeSettings,
) -> None:
    client, _, _ = _build_client(make_settings)
    _login(client)
    private_draft_id = client.post("/roadmaps", json=_COMPLETE_ROADMAP).json()["id"]
    public_id = _create_published_public(client)
    assert (
        client.put(f"/roadmaps/{public_id}/visibility", json={"visibility": "private"}).status_code
        == 200
    )

    client.cookies.clear()
    private_draft = client.get(f"/roadmaps/{private_draft_id}")
    private_published = client.get(f"/roadmaps/{public_id}")
    assert private_draft.status_code == 404
    assert private_published.status_code == 404


def test_spoofed_owner_header_without_cookie_does_not_grant_private_access(
    make_settings: MakeSettings,
) -> None:
    client, _, _ = _build_client(make_settings)
    _login(client)
    roadmap_id = client.post("/roadmaps", json=_COMPLETE_ROADMAP).json()["id"]
    client.cookies.clear()

    response = client.get(f"/roadmaps/{roadmap_id}", headers={"X-User-ID": "owner"})
    assert response.status_code == 404


def test_invalid_cookie_is_not_downgraded_to_anonymous(
    make_settings: MakeSettings,
) -> None:
    client, _, _ = _build_client(make_settings)
    response = client.get("/roadmaps/unknown-0000", headers={"Cookie": "wren_session=invalid"})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_public_to_private_revocation_takes_effect_on_next_anonymous_read(
    make_settings: MakeSettings,
) -> None:
    client, _, _ = _build_client(make_settings)
    _login(client)
    roadmap_id = _create_published_public(client)
    client.cookies.clear()
    assert client.get(f"/roadmaps/{roadmap_id}").status_code == 200

    login_response = client.post(
        "/auth/login", json={"email": "owner@example.com", "password": _PASSWORD}
    )
    assert login_response.status_code == 200
    assert (
        client.put(f"/roadmaps/{roadmap_id}/visibility", json={"visibility": "private"}).status_code
        == 200
    )
    client.cookies.clear()
    response = client.get(f"/roadmaps/{roadmap_id}")
    assert response.status_code == 404


def test_all_protected_external_routes_reject_missing_identity(
    make_settings: MakeSettings,
) -> None:
    client, _, _ = _build_client(make_settings)
    requests: list[tuple[str, str, object | None, dict[str, str] | None]] = [
        ("post", "/roadmaps", _COMPLETE_ROADMAP, None),
        ("patch", "/roadmaps/unknown-0000", {"operations": []}, {"If-Match": "1"}),
        ("put", "/roadmaps/unknown-0000", _COMPLETE_ROADMAP, {"If-Match": "1"}),
        ("post", "/roadmaps/unknown-0000:validate", None, None),
        ("post", "/roadmaps/unknown-0000:publish", None, None),
        ("post", "/roadmaps/unknown-0000:fork", None, None),
        ("patch", "/roadmaps/unknown-0000/metadata", {"title": "x"}, None),
        ("put", "/roadmaps/unknown-0000/visibility", {"visibility": "private"}, None),
        ("post", "/roadmaps/unknown-0000:archive", None, None),
        ("delete", "/roadmaps/unknown-0000", None, None),
        ("post", "/roadmaps/unknown-0000/follow", None, None),
        ("get", "/roadmaps/unknown-0000/progress", None, None),
        ("post", "/roadmaps/unknown-0000/progress", {"item_ids": [], "state": "complete"}, None),
        ("get", "/roadmaps/unknown-0000/next", None, None),
        ("put", "/roadmaps/unknown-0000/deadline", {"deadline": None}, None),
        ("get", "/roadmaps/unknown-0000/overview", None, None),
        ("get", "/roadmaps/unknown-0000/nodes/node", None, None),
        ("get", "/roadmaps/unknown-0000/sections/section", None, None),
        ("get", "/roadmaps/unknown-0000/search", None, None),
        ("get", "/me/dashboard", None, None),
    ]
    for method, path, payload, headers in requests:
        response = client.request(method.upper(), path, json=payload, headers=headers)
        assert response.status_code == 401, f"{method.upper()} {path}: {response.text}"
