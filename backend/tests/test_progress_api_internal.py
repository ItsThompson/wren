"""Contract tests for the internal progress surface (:8001).

The internal app is the surface the MCP progress tools call: it
resolves identity from the trusted ``X-User-ID`` header behind the shared
``INTERNAL_API_TOKEN``, not a session cookie. These assert the
trust boundary (``require_internal_user``) and that every query stays per-user
scoped so a tool can never reach another user's progress even though the identity
is injected. The service is backed by in-memory repositories seeded with a
published roadmap; no database is required.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.support.fakes.progress_builders import CHK_ARRAYS_READ, build_roadmap, make_record
from tests.support.fakes.progress_fakes import InMemoryProgressRepository
from tests.support.fakes.roadmaps_fakes import InMemoryRoadmapRepository
from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.identity import (
    INTERNAL_TOKEN_HEADER,
    USER_ID_HEADER,
)
from wren.core.route_registry import App
from wren.core.settings import AppSettings
from wren.progress.router import create_progress_router
from wren.progress.service import ProgressService

if TYPE_CHECKING:
    from fastapi import FastAPI

MakeSettings = Callable[..., AppSettings]

_INTERNAL_TOKEN = "test-internal-token"
_USER = "user-ada"
_OTHER_USER = "user-grace"
ROADMAP_ID = "grokking-dsa-7f3k"


def _build_client(make_settings: MakeSettings) -> TestClient:
    roadmap_repo = InMemoryRoadmapRepository()
    roadmap = build_roadmap()
    roadmap_repo._by_id[roadmap.id] = make_record(roadmap)
    progress_repo = InMemoryProgressRepository()

    def progress_provider() -> ProgressService:
        return ProgressService(roadmap_repo, progress_repo)

    app: FastAPI = create_app(
        make_settings(),
        routers=[create_progress_router(progress_provider, app=App.INTERNAL)],
        exception_handlers=build_exception_handlers(),
    )
    app.state.internal_api_token = SecretStr(_INTERNAL_TOKEN)
    return TestClient(app)


def _trusted(user_id: str = _USER) -> dict[str, str]:
    return {INTERNAL_TOKEN_HEADER: _INTERNAL_TOKEN, USER_ID_HEADER: user_id}


def test_web_only_follow_and_deadline_are_not_mounted(make_settings: MakeSettings) -> None:
    # follow and deadline are web-only (external app only); the internal app the
    # MCP server calls never mounts them, so both are 404 even over the trusted
    # identity (no route, not an auth failure).
    client = _build_client(make_settings)
    follow = client.post(f"/roadmaps/{ROADMAP_ID}/follow", headers=_trusted())
    assert follow.status_code == 404, follow.text
    deadline = client.put(
        f"/roadmaps/{ROADMAP_ID}/deadline", headers=_trusted(), json={"deadline": "2026-12-01"}
    )
    assert deadline.status_code == 404, deadline.text


def test_update_over_the_trusted_identity(make_settings: MakeSettings) -> None:
    client = _build_client(make_settings)
    response = client.post(
        f"/roadmaps/{ROADMAP_ID}/progress",
        headers=_trusted(),
        json={"item_ids": [CHK_ARRAYS_READ], "state": "complete"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["progress"]["checked_items"] == 1


def test_get_and_next_over_the_trusted_identity(make_settings: MakeSettings) -> None:
    client = _build_client(make_settings)
    assert client.get(f"/roadmaps/{ROADMAP_ID}/progress", headers=_trusted()).status_code == 200
    next_response = client.get(
        f"/roadmaps/{ROADMAP_ID}/next", headers=_trusted(), params={"format": "detailed"}
    )
    assert next_response.status_code == 200
    body = next_response.json()
    # The MCP roadmap_get_next tool reads this: full shape + detailed
    # path_position, structural why_now, remaining_in_path.
    assert body["remaining_in_path"] == 3
    assert all(item["path_position"] == 1 for item in body["items"])
    assert "suggested path" in body["items"][0]["why_now"].lower()


def test_progress_is_scoped_per_trusted_user(make_settings: MakeSettings) -> None:
    # Per-user scoping holds even though the internal app trusts X-User-ID: one
    # user's update is invisible to another.
    client = _build_client(make_settings)
    client.post(
        f"/roadmaps/{ROADMAP_ID}/progress",
        headers=_trusted(),
        json={"item_ids": [CHK_ARRAYS_READ], "state": "complete"},
    )
    snapshot = client.get(
        f"/roadmaps/{ROADMAP_ID}/progress",
        headers=_trusted(_OTHER_USER),
        params={"detailed": True},
    ).json()
    assert snapshot["checked_items"] == 0
    assert snapshot["checked_ids"] == []
