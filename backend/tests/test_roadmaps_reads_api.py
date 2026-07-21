"""Contract tests for the external read-projection surface.

Asserts the read projections over real HTTP on an external-shaped app
(overview / node / paginated section / search), the ``concise|detailed`` switch,
opaque-cursor pagination, resource-links-not-bodies, the public non-owner read
(public+published readable by anyone, private -> 404, archived rules),
and per-user scoping of the progress-derived counts. The roadmaps + progress
services are backed by in-memory repositories sharing one roadmap store and one
progress store, so a POST to the progress endpoint is visible to the read
projections' checked reader (as the production wiring binds them).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from tests.roadmaps_read_builders import (
    CHK_ARRAYS_READ,
    ROADMAP_ID,
    SUB_ARRAYS,
    SUB_HASHING,
    build_read_roadmap,
    checked_reader_over,
)
from tests.support.fakes.accounts_fakes import (
    InMemoryAccountRepository,
    build_test_codec,
    build_test_hasher,
)
from tests.support.fakes.progress_builders import make_record
from tests.support.fakes.progress_fakes import InMemoryProgressRepository
from tests.support.fakes.roadmaps_fakes import InMemoryRoadmapRepository
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
from wren.roadmaps.read_service import RoadmapReadService
from wren.roadmaps.router import create_roadmaps_router
from wren.roadmaps.schemas import Roadmap, RoadmapStatus, Visibility
from wren.roadmaps.service import RoadmapService

if TYPE_CHECKING:
    from fastapi import FastAPI

MakeSettings = Callable[..., AppSettings]

_PASSWORD = "Str0ngPass"


def _build_client(
    make_settings: MakeSettings, *roadmaps: Roadmap, page_size: int = 20
) -> tuple[TestClient, InMemoryProgressRepository]:
    """An external-shaped app with /auth + roadmaps + progress routers over shared
    in-memory repos, the roadmap repo pre-seeded with the given roadmap(s) (a
    published public roadmap owned by ``author`` by default). The roadmaps service
    resolves the caller's checked set from the SAME progress repo the progress
    router writes to, so a POST /progress feeds the read projections."""
    account_repo = InMemoryAccountRepository()
    codec = build_test_codec()
    hasher = build_test_hasher()
    roadmap_repo = InMemoryRoadmapRepository()
    for roadmap in roadmaps or (build_read_roadmap(),):
        roadmap_repo._by_id[roadmap.id] = make_record(roadmap)
    progress_repo = InMemoryProgressRepository()

    def account_provider() -> AccountService:
        return AccountService(account_repo, hasher, codec)

    def roadmap_provider() -> RoadmapService:
        return RoadmapService(
            roadmap_repo,
            follower_counter=progress_repo.count_followers,
        )

    def read_provider() -> RoadmapReadService:
        return RoadmapReadService(
            roadmap_repo,
            checked_reader=checked_reader_over(progress_repo),
            section_page_size=page_size,
        )

    def progress_provider() -> ProgressService:
        return ProgressService(roadmap_repo, progress_repo)

    accounts_router = create_accounts_router(
        account_provider, cookie_config=CookieConfig(secure=False, domain=None)
    )
    app: FastAPI = create_app(
        make_settings(),
        routers=[
            accounts_router,
            create_roadmaps_router(roadmap_provider, read_provider, app=App.EXTERNAL),
            create_progress_router(progress_provider, app=App.EXTERNAL),
        ],
        exception_handlers=build_exception_handlers(),
    )
    app.state.session_verifier = create_session_verifier(codec, account_repo.is_session_revoked)
    app.add_middleware(StripInboundIdentityMiddleware)
    return TestClient(app), progress_repo


def _login(client: TestClient, username: str = "ada", email: str = "ada@example.com") -> None:
    response = client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": _PASSWORD},
    )
    assert response.status_code == 201, response.text


def _check(client: TestClient, *item_ids: str) -> None:
    """Set the logged-in caller's given items complete via the progress endpoint."""
    response = client.post(
        f"/roadmaps/{ROADMAP_ID}/progress",
        json={"item_ids": list(item_ids), "state": "complete"},
    )
    assert response.status_code == 200, response.text


# --- overview ---------------------------------------------------------------


def test_overview_returns_sections_in_order_with_counts_and_no_bodies(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    body = client.get(f"/roadmaps/{ROADMAP_ID}/overview").json()
    assert body["roadmap_id"] == ROADMAP_ID
    assert [section["section_id"] for section in body["sections"]] == ["sec_core", "sec_advanced"]
    assert body["overall"]["total_items"] == 4
    assert body["overall"]["checked_items"] == 0
    # No checklist-item bodies in the orientation projection.
    assert "items" not in body["sections"][0]


def test_overview_counts_reflect_the_callers_progress(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    _check(client, CHK_ARRAYS_READ)
    body = client.get(f"/roadmaps/{ROADMAP_ID}/overview").json()
    assert body["overall"]["checked_items"] == 1
    assert body["overall"]["percent"] == 25


def test_overview_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    assert client.get(f"/roadmaps/{ROADMAP_ID}/overview").status_code == 401


# --- node -------------------------------------------------------------------


def test_node_concise_omits_description_detailed_includes_it(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    concise = client.get(f"/roadmaps/{ROADMAP_ID}/nodes/{SUB_ARRAYS}").json()
    assert concise["subsection_id"] == SUB_ARRAYS
    assert concise["description"] is None
    # Concise still carries the follow-up IDs (items + resource links).
    assert [item["id"] for item in concise["items"]] == ["chk_arrays-read", "chk_arrays-drill"]
    detailed = client.get(
        f"/roadmaps/{ROADMAP_ID}/nodes/{SUB_ARRAYS}", params={"format": "detailed"}
    ).json()
    assert detailed["description"] == "Two-pointer and sliding-window patterns."


def test_node_resources_are_links_and_prereqs_resolve_with_done(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    _check(client, "chk_arrays-read", "chk_arrays-drill")
    body = client.get(f"/roadmaps/{ROADMAP_ID}/nodes/{SUB_HASHING}").json()
    # Arrays is fully done -> the hashing prereq resolves to done True with a title.
    assert body["prereqs"] == [{"id": SUB_ARRAYS, "title": "Arrays", "done": True}]
    # Its own item is not yet done.
    assert body["items"][0]["done"] is False
    node_arrays = client.get(f"/roadmaps/{ROADMAP_ID}/nodes/{SUB_ARRAYS}").json()
    guide = node_arrays["resources"][0]
    assert guide["url"].startswith("https://") and set(guide) == {"id", "title", "url", "type"}


def test_node_unknown_id_is_404_naming_valid_siblings(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    response = client.get(f"/roadmaps/{ROADMAP_ID}/nodes/sub_ghost")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert SUB_ARRAYS in body["detail"] and SUB_HASHING in body["detail"]


# --- section (paginated) ----------------------------------------------------


def test_section_returns_a_page_with_include(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    body = client.get(
        f"/roadmaps/{ROADMAP_ID}/sections/sec_core", params={"include": "items"}
    ).json()
    assert body["section_id"] == "sec_core"
    assert body["include"] == "items"
    assert body["next_cursor"] is None
    assert body["subsections"][0]["items"]
    assert body["subsections"][0]["resources"] == []


def test_section_truncates_and_follows_the_cursor(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, page_size=1)
    _login(client)
    first = client.get(f"/roadmaps/{ROADMAP_ID}/sections/sec_core").json()
    assert [node["subsection_id"] for node in first["subsections"]] == [SUB_ARRAYS]
    assert first["next_cursor"] is not None
    assert "showing 1 of 2" in first["steering"]
    second = client.get(
        f"/roadmaps/{ROADMAP_ID}/sections/sec_core", params={"cursor": first["next_cursor"]}
    ).json()
    assert [node["subsection_id"] for node in second["subsections"]] == [SUB_HASHING]
    assert second["next_cursor"] is None


def test_section_bad_cursor_is_a_422(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    response = client.get(f"/roadmaps/{ROADMAP_ID}/sections/sec_core", params={"cursor": "!!bad!!"})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert "cursor" in response.json()["fields"]


def test_section_unknown_id_is_404(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    response = client.get(f"/roadmaps/{ROADMAP_ID}/sections/sec_ghost")
    assert response.status_code == 404
    assert "sec_core" in response.json()["detail"]


# --- search -----------------------------------------------------------------


def test_search_by_keyword_and_by_tag(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    by_keyword = client.get(f"/roadmaps/{ROADMAP_ID}/search", params={"q": "graphs"}).json()
    assert any(hit["subsection_id"] == "sub_graphs" for hit in by_keyword)
    by_tag = client.get(f"/roadmaps/{ROADMAP_ID}/search", params={"tags": "two-pointers"}).json()
    assert by_tag == [
        {
            "kind": "subsection",
            "subsection_id": SUB_ARRAYS,
            "item_id": None,
            "title_or_text": "Arrays",
            "matched_tags": ["two-pointers"],
        }
    ]


def test_search_without_query_or_tags_is_empty(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    assert client.get(f"/roadmaps/{ROADMAP_ID}/search").json() == []


# --- public non-owner read --------------------------------------------------


def test_non_owner_can_read_a_public_published_roadmap(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)  # owned by "author", published + public
    _login(client, username="reader", email="reader@example.com")
    assert client.get(f"/roadmaps/{ROADMAP_ID}").status_code == 200
    assert client.get(f"/roadmaps/{ROADMAP_ID}/overview").status_code == 200
    assert client.get(f"/roadmaps/{ROADMAP_ID}/nodes/{SUB_ARRAYS}").status_code == 200


def test_non_owner_gets_404_on_a_private_roadmap(make_settings: MakeSettings) -> None:
    private = build_read_roadmap(owner="author", visibility=Visibility.PRIVATE)
    client, _ = _build_client(make_settings, private)
    _login(client, username="reader", email="reader@example.com")
    assert client.get(f"/roadmaps/{ROADMAP_ID}").status_code == 404
    assert client.get(f"/roadmaps/{ROADMAP_ID}/overview").status_code == 404


def test_non_owner_gets_404_on_a_public_draft(make_settings: MakeSettings) -> None:
    # A public *draft* is not discoverable: a non-owner cannot read it (no leak).
    draft = build_read_roadmap(status=RoadmapStatus.DRAFT, visibility=Visibility.PUBLIC)
    client, _ = _build_client(make_settings, draft)
    _login(client, username="reader", email="reader@example.com")
    assert client.get(f"/roadmaps/{ROADMAP_ID}/overview").status_code == 404


def test_non_owner_can_read_a_public_archived_roadmap_by_link(make_settings: MakeSettings) -> None:
    # Archived is hidden from discovery but still readable by direct link.
    archived = build_read_roadmap(status=RoadmapStatus.ARCHIVED, visibility=Visibility.PUBLIC)
    client, _ = _build_client(make_settings, archived)
    _login(client, username="reader", email="reader@example.com")
    assert client.get(f"/roadmaps/{ROADMAP_ID}/overview").status_code == 200


# --- per-user scoping -------------------------------------------------------


def test_overview_progress_is_scoped_per_user(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client, username="owner", email="owner@example.com")
    _check(client, CHK_ARRAYS_READ)
    assert client.get(f"/roadmaps/{ROADMAP_ID}/overview").json()["overall"]["checked_items"] == 1

    client.cookies.clear()
    _login(client, username="other", email="other@example.com")
    body = client.get(f"/roadmaps/{ROADMAP_ID}/overview").json()
    assert body["overall"]["checked_items"] == 0
