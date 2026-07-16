"""Contract tests for the internal read-projection surface (:8001).

The internal app is the surface the MCP read tools call: it resolves
identity from the trusted ``X-User-ID`` header behind ``INTERNAL_API_TOKEN``, not a
session cookie. These assert the four read routes resolve over
the trusted identity, stay per-user scoped (a tool cannot read another user's
progress-derived counts), and honor the same readability rule as the external
app. The roadmaps + progress services share one in-memory roadmap store and one
progress store so a trusted POST /progress feeds the read projections.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from progress_builders import make_record
from progress_fakes import InMemoryProgressRepository
from roadmaps_fakes import InMemoryRoadmapRepository
from roadmaps_read_builders import (
    CHK_ARRAYS_READ,
    ROADMAP_ID,
    SUB_ARRAYS,
    SUB_HASHING,
    build_read_roadmap,
    checked_reader_over,
)
from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.identity import (
    INTERNAL_TOKEN_HEADER,
    USER_ID_HEADER,
    require_internal_user,
)
from wren.core.settings import AppSettings
from wren.progress.router import create_progress_router
from wren.progress.service import ProgressService
from wren.roadmaps.read_service import RoadmapReadService
from wren.roadmaps.router import create_roadmaps_router
from wren.roadmaps.schemas import Roadmap
from wren.roadmaps.service import RoadmapService

MakeSettings = Callable[..., AppSettings]

_INTERNAL_TOKEN = "test-internal-token"
_USER = "user-ada"
_OTHER_USER = "user-grace"


def _build_client(
    make_settings: MakeSettings, *roadmaps: Roadmap
) -> tuple[TestClient, InMemoryProgressRepository]:
    """An internal-shaped app with the internal roadmaps + progress routers over
    shared in-memory repos, the roadmap repo pre-seeded with a published public
    roadmap. Trusts X-User-ID (no cookie verifier / identity strip)."""
    roadmap_repo = InMemoryRoadmapRepository()
    for roadmap in roadmaps or (build_read_roadmap(),):
        roadmap_repo._by_id[roadmap.id] = make_record(roadmap)
    progress_repo = InMemoryProgressRepository()

    def roadmap_provider() -> RoadmapService:
        return RoadmapService(
            roadmap_repo,
            follower_counter=progress_repo.count_followers,
        )

    def read_provider() -> RoadmapReadService:
        return RoadmapReadService(
            roadmap_repo,
            checked_reader=checked_reader_over(progress_repo),
        )

    def progress_provider() -> ProgressService:
        return ProgressService(roadmap_repo, progress_repo)

    app: FastAPI = create_app(
        make_settings(),
        routers=[
            create_roadmaps_router(roadmap_provider, read_provider, identity=require_internal_user),
            create_progress_router(progress_provider, identity=require_internal_user),
        ],
        exception_handlers=build_exception_handlers(),
    )
    app.state.internal_api_token = _INTERNAL_TOKEN
    return TestClient(app), progress_repo


def _trusted(user_id: str = _USER) -> dict[str, str]:
    return {INTERNAL_TOKEN_HEADER: _INTERNAL_TOKEN, USER_ID_HEADER: user_id}


# --- trust boundary ---------------------------------------------------------


def test_overview_without_the_internal_token_is_401(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.get(f"/roadmaps/{ROADMAP_ID}/overview", headers={USER_ID_HEADER: _USER})
    assert response.status_code == 401


# --- the four read routes over the trusted identity -------------------------


def test_overview_resolves_over_the_trusted_identity(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    body = client.get(f"/roadmaps/{ROADMAP_ID}/overview", headers=_trusted()).json()
    assert [section["section_id"] for section in body["sections"]] == ["sec_core", "sec_advanced"]


def test_node_resolves_and_honors_the_format_switch(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    concise = client.get(f"/roadmaps/{ROADMAP_ID}/nodes/{SUB_ARRAYS}", headers=_trusted()).json()
    assert concise["description"] is None
    detailed = client.get(
        f"/roadmaps/{ROADMAP_ID}/nodes/{SUB_ARRAYS}",
        params={"format": "detailed"},
        headers=_trusted(),
    ).json()
    assert detailed["description"]


def test_section_and_search_resolve_over_the_trusted_identity(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings)
    section = client.get(f"/roadmaps/{ROADMAP_ID}/sections/sec_core", headers=_trusted()).json()
    assert [node["subsection_id"] for node in section["subsections"]] == [SUB_ARRAYS, SUB_HASHING]
    search = client.get(
        f"/roadmaps/{ROADMAP_ID}/search", params={"q": "hashing"}, headers=_trusted()
    ).json()
    assert any(hit["subsection_id"] == SUB_HASHING for hit in search)


# --- per-user scoping on the trusted surface --------------------------------


def test_overview_counts_are_scoped_to_the_trusted_user(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    checked = client.post(
        f"/roadmaps/{ROADMAP_ID}/progress",
        json={"item_ids": [CHK_ARRAYS_READ], "state": "complete"},
        headers=_trusted(_USER),
    )
    assert checked.status_code == 200, checked.text
    mine = client.get(f"/roadmaps/{ROADMAP_ID}/overview", headers=_trusted(_USER)).json()
    assert mine["overall"]["checked_items"] == 1
    # A different trusted user sees none of the first user's progress.
    theirs = client.get(f"/roadmaps/{ROADMAP_ID}/overview", headers=_trusted(_OTHER_USER)).json()
    assert theirs["overall"]["checked_items"] == 0
