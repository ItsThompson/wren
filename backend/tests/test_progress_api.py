"""Contract tests for the external progress surface on an external-shaped app.

Asserts the RFC 9457 problem+json shapes and the status codes over
real HTTP: follow is 201 (409 on a draft), progress update is explicit-set +
idempotent (422 on a foreign item id, applying nothing), get returns the derived
snapshot, next is server-computed, ``require_user`` gates the surface (401
anonymous), and progress is scoped per user. The services are backed by in-memory
repositories seeded with a published roadmap; no database is required.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from accounts_fakes import InMemoryAccountRepository, build_test_codec, build_test_hasher
from progress_builders import (
    CHK_ARRAYS_DRILL,
    CHK_ARRAYS_READ,
    CHK_HASH,
    SUB_ARRAYS,
    build_roadmap,
    make_record,
)
from progress_fakes import InMemoryProgressRepository
from roadmaps_fakes import InMemoryRoadmapRepository
from wren.accounts.api import create_accounts_router
from wren.accounts.config import CookieConfig
from wren.accounts.service import AccountService
from wren.accounts.session import create_session_verifier
from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.identity import StripInboundIdentityMiddleware
from wren.core.settings import AppSettings
from wren.progress.api import create_progress_router
from wren.progress.service import ProgressService
from wren.roadmaps.schemas import Roadmap, RoadmapStatus, Visibility

MakeSettings = Callable[..., AppSettings]

_PASSWORD = "Str0ngPass"
ROADMAP_ID = "grokking-dsa-7f3k"


def _build_client(
    make_settings: MakeSettings, *roadmaps: Roadmap
) -> tuple[TestClient, InMemoryProgressRepository]:
    """An external-shaped app with /auth + progress routers over in-memory repos,
    the roadmap repo pre-seeded with the given published roadmap(s)."""
    account_repo = InMemoryAccountRepository()
    codec = build_test_codec()
    hasher = build_test_hasher()
    roadmap_repo = InMemoryRoadmapRepository()
    for roadmap in roadmaps or (build_roadmap(),):
        roadmap_repo._by_id[roadmap.id] = make_record(roadmap)
    progress_repo = InMemoryProgressRepository()

    def account_provider() -> AccountService:
        return AccountService(account_repo, hasher, codec)

    def progress_provider() -> ProgressService:
        return ProgressService(roadmap_repo, progress_repo)

    accounts_router = create_accounts_router(
        account_provider, cookie_config=CookieConfig(secure=False, domain=None)
    )
    progress_router = create_progress_router(progress_provider)

    app: FastAPI = create_app(
        make_settings(),
        routers=[accounts_router, progress_router],
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


# --- follow -----------------------------------------------------------------


def test_follow_a_published_roadmap_is_201(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    response = client.post(f"/roadmaps/{ROADMAP_ID}/follow")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["roadmap_id"] == ROADMAP_ID
    assert body["checked"] == {}


def test_follow_a_draft_is_a_409(make_settings: MakeSettings) -> None:
    draft = build_roadmap(status=RoadmapStatus.DRAFT, visibility=Visibility.PUBLIC)
    client, _ = _build_client(make_settings, draft)
    _login(client)
    response = client.post(f"/roadmaps/{draft.id}/follow")
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "CONFLICT"


def test_follow_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post(f"/roadmaps/{ROADMAP_ID}/follow")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_follow_a_private_roadmap_owned_by_another_is_a_404(make_settings: MakeSettings) -> None:
    private = build_roadmap(owner="someone", visibility=Visibility.PRIVATE)
    client, _ = _build_client(make_settings, private)
    _login(client)
    response = client.post(f"/roadmaps/{private.id}/follow")
    assert response.status_code == 404


# --- progress update (explicit set) -----------------------------------------


def test_update_sets_items_and_returns_snapshot_plus_next(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    response = client.post(
        f"/roadmaps/{ROADMAP_ID}/progress",
        json={"item_ids": [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL], "state": "complete"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["progress"]["checked_items"] == 2
    assert sorted(body["progress"]["checked_ids"]) == sorted([CHK_ARRAYS_READ, CHK_ARRAYS_DRILL])
    assert [item["item_id"] for item in body["next"]["items"]] == [CHK_HASH]


def test_update_is_idempotent(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    body = {"item_ids": [CHK_ARRAYS_READ], "state": "complete"}
    first = client.post(f"/roadmaps/{ROADMAP_ID}/progress", json=body).json()
    second = client.post(f"/roadmaps/{ROADMAP_ID}/progress", json=body).json()
    assert (
        first["progress"]["checked_ids"] == second["progress"]["checked_ids"] == [CHK_ARRAYS_READ]
    )


def test_update_with_a_foreign_item_id_is_a_422_applying_nothing(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    response = client.post(
        f"/roadmaps/{ROADMAP_ID}/progress",
        json={"item_ids": [CHK_ARRAYS_READ, "chk_ghost"], "state": "complete"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION"
    assert "item_ids" in body["fields"]
    # Nothing applied: a fresh read shows zero checked.
    snapshot = client.get(f"/roadmaps/{ROADMAP_ID}/progress").json()
    assert snapshot["checked_items"] == 0


def test_update_empty_item_ids_is_a_422(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    response = client.post(
        f"/roadmaps/{ROADMAP_ID}/progress", json={"item_ids": [], "state": "complete"}
    )
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


# --- get progress -----------------------------------------------------------


def test_get_progress_default_is_concise(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    body = client.get(f"/roadmaps/{ROADMAP_ID}/progress").json()
    assert body["total_items"] == 4
    assert body["checked_ids"] is None


def test_get_progress_detailed_lists_checked_ids(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    client.post(
        f"/roadmaps/{ROADMAP_ID}/progress",
        json={"item_ids": [CHK_ARRAYS_READ], "state": "complete"},
    )
    body = client.get(f"/roadmaps/{ROADMAP_ID}/progress", params={"detailed": True}).json()
    assert body["checked_ids"] == [CHK_ARRAYS_READ]


# --- next -------------------------------------------------------------------


def test_get_next_is_server_computed(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    body = client.get(f"/roadmaps/{ROADMAP_ID}/next").json()
    assert body["complete"] is False
    assert [item["item_id"] for item in body["items"]] == [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL]
    # Full get_next shape: structural why_now + remaining_in_path; concise omits
    # path_position.
    assert body["remaining_in_path"] == 3
    first = body["items"][0]
    assert "suggested path" in first["why_now"].lower()
    assert first["path_position"] is None
    assert first["resources"][0]["url"] == f"https://x.test/{SUB_ARRAYS}"


def test_get_next_detailed_includes_path_position(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    body = client.get(f"/roadmaps/{ROADMAP_ID}/next", params={"format": "detailed"}).json()
    assert all(item["path_position"] == 1 for item in body["items"])


def test_get_next_reports_completion(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    client.post(
        f"/roadmaps/{ROADMAP_ID}/progress",
        json={
            "item_ids": [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL, CHK_HASH, "chk_graphs"],
            "state": "complete",
        },
    )
    body = client.get(f"/roadmaps/{ROADMAP_ID}/next").json()
    assert body["complete"] is True
    assert body["items"] == []


# --- per-user scoping -------------------------------------------------------


def test_progress_is_scoped_per_user(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client, username="owner", email="owner@example.com")
    client.post(
        f"/roadmaps/{ROADMAP_ID}/progress",
        json={"item_ids": [CHK_ARRAYS_READ], "state": "complete"},
    )

    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    snapshot = client.get(f"/roadmaps/{ROADMAP_ID}/progress", params={"detailed": True}).json()
    assert snapshot["checked_items"] == 0
    assert snapshot["checked_ids"] == []


# --- deadline (set / clear) -------------------------------------------------


def test_set_deadline_sets_and_echoes_it_on_the_snapshot(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    response = client.put(f"/roadmaps/{ROADMAP_ID}/deadline", json={"deadline": "2026-12-01"})
    assert response.status_code == 200, response.text
    assert response.json()["deadline"] == "2026-12-01"
    # The progress snapshot carries the deadline for the countdown UI.
    snapshot = client.get(f"/roadmaps/{ROADMAP_ID}/progress").json()
    assert snapshot["deadline"] == "2026-12-01"


def test_clear_deadline_with_null(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    client.put(f"/roadmaps/{ROADMAP_ID}/deadline", json={"deadline": "2026-12-01"})
    cleared = client.put(f"/roadmaps/{ROADMAP_ID}/deadline", json={"deadline": None})
    assert cleared.status_code == 200
    assert cleared.json()["deadline"] is None
    assert client.get(f"/roadmaps/{ROADMAP_ID}/progress").json()["deadline"] is None


def test_set_deadline_in_the_past_is_allowed(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    response = client.put(f"/roadmaps/{ROADMAP_ID}/deadline", json={"deadline": "2000-01-01"})
    assert response.status_code == 200
    assert response.json()["deadline"] == "2000-01-01"


def test_set_deadline_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.put(f"/roadmaps/{ROADMAP_ID}/deadline", json={"deadline": "2026-12-01"})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_set_deadline_on_a_draft_is_a_409(make_settings: MakeSettings) -> None:
    draft = build_roadmap(status=RoadmapStatus.DRAFT, visibility=Visibility.PUBLIC)
    client, _ = _build_client(make_settings, draft)
    _login(client)
    response = client.put(f"/roadmaps/{draft.id}/deadline", json={"deadline": "2026-12-01"})
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


def test_deadline_is_scoped_per_user(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client, username="owner", email="owner@example.com")
    client.put(f"/roadmaps/{ROADMAP_ID}/deadline", json={"deadline": "2026-12-01"})

    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    snapshot = client.get(f"/roadmaps/{ROADMAP_ID}/progress").json()
    assert snapshot["deadline"] is None
