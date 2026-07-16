"""End-to-end runtime check: the full study spine over the assembled app + Postgres.

Boots an external-shaped app with the production wiring (request-scoped
SQLAlchemy repositories via ``get_session``, the real session verifier) against a
migrated ``postgres:17-alpine`` and drives the full walking-skeleton spine over
HTTP: register -> create -> publish -> follow -> check -> get_next. Also proves
the security invariants at runtime: following a draft is a 409, and a second
user's progress is empty (per-user scoping). Skipped when Docker is unavailable.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

from accounts_fakes import build_test_codec, build_test_hasher
from wren.accounts.api import create_accounts_router
from wren.accounts.config import CookieConfig
from wren.accounts.session import build_revocation_lookup, create_session_verifier
from wren.accounts.wiring import build_account_service_provider
from wren.core.app_factory import create_app
from wren.core.db import create_database
from wren.core.errors import build_exception_handlers
from wren.core.identity import StripInboundIdentityMiddleware
from wren.core.settings import AppSettings
from wren.progress.api import create_progress_router
from wren.progress.wiring import build_progress_service_provider
from wren.roadmaps.api import create_roadmaps_router
from wren.roadmaps.wiring import (
    build_roadmap_read_service_provider,
    build_roadmap_service_provider,
)

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
_PASSWORD = "Str0ngPass"
MakeSettings = Callable[..., AppSettings]

_PUBLISHABLE_ROADMAP = {
    "title": "Grokking DSA",
    "visibility": "public",
    "suggested_path": ["sub_arrays", "sub_hashing"],
    "sections": [
        {
            "title": "Foundations",
            "subsections": [
                {
                    "proposed_id": "sub_arrays",
                    "title": "Arrays",
                    "resources": [{"title": "Guide", "url": "https://x.test", "type": "article"}],
                    "checklist_items": [
                        {"proposed_id": "chk_read", "text": "Read it"},
                        {"proposed_id": "chk_drill", "text": "Drill it"},
                    ],
                },
                {
                    "proposed_id": "sub_hashing",
                    "title": "Hashing",
                    "prereq_ids": ["sub_arrays"],
                    "resources": [{"title": "Vid", "url": "https://y.test", "type": "video"}],
                    "checklist_items": [{"proposed_id": "chk_hash", "text": "Implement a counter"}],
                },
            ],
        }
    ],
}


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> Iterator[str]:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", postgres_url)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = postgres_url
    try:
        command.upgrade(config, "head")
        yield postgres_url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _external_app(database_url: str, settings: AppSettings) -> FastAPI:
    database = create_database(database_url)
    codec = build_test_codec()
    hasher = build_test_hasher()
    accounts_router = create_accounts_router(
        build_account_service_provider(hasher, codec),
        cookie_config=CookieConfig(secure=False, domain=None),
    )
    roadmaps_router = create_roadmaps_router(
        build_roadmap_service_provider(), build_roadmap_read_service_provider()
    )
    progress_router = create_progress_router(build_progress_service_provider())
    app = create_app(
        settings,
        routers=[accounts_router, roadmaps_router, progress_router],
        exception_handlers=build_exception_handlers(),
    )
    app.state.db = database
    app.state.session_verifier = create_session_verifier(codec, build_revocation_lookup(database))
    app.add_middleware(StripInboundIdentityMiddleware)
    return app


def _register(client: TestClient, username: str, email: str) -> None:
    response = client.post(
        "/auth/register", json={"username": username, "email": email, "password": _PASSWORD}
    )
    assert response.status_code == 201, response.text


def test_full_study_spine_end_to_end_over_http(
    migrated_url: str, make_settings: MakeSettings
) -> None:
    app = _external_app(migrated_url, make_settings(database_url=migrated_url))
    with TestClient(app) as client:
        _register(client, "progstudy", "prog-study@example.com")

        # create -> publish
        roadmap_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]
        assert client.post(f"/roadmaps/{roadmap_id}:publish").status_code == 200

        # follow creates the private progress record
        follow = client.post(f"/roadmaps/{roadmap_id}/follow")
        assert follow.status_code == 201, follow.text
        assert follow.json()["checked"] == {}

        # next starts at the first subsection's items
        first_next = client.get(f"/roadmaps/{roadmap_id}/next").json()
        assert [item["item_id"] for item in first_next["items"]] == ["chk_read", "chk_drill"]
        assert first_next["complete"] is False
        # full get_next shape: structural why_now + remaining_in_path (2 subsections)
        assert first_next["remaining_in_path"] == 2
        assert "suggested path" in first_next["items"][0]["why_now"].lower()
        # detailed adds path_position (concise omitted it)
        assert first_next["items"][0]["path_position"] is None
        detailed_next = client.get(
            f"/roadmaps/{roadmap_id}/next", params={"format": "detailed"}
        ).json()
        assert all(item["path_position"] == 1 for item in detailed_next["items"])

        # check the arrays items -> next advances to hashing
        update = client.post(
            f"/roadmaps/{roadmap_id}/progress",
            json={"item_ids": ["chk_read", "chk_drill"], "state": "complete"},
        )
        assert update.status_code == 200, update.text
        body = update.json()
        assert body["progress"]["checked_items"] == 2
        assert [item["item_id"] for item in body["next"]["items"]] == ["chk_hash"]

        # finish everything -> completion is reported
        client.post(
            f"/roadmaps/{roadmap_id}/progress",
            json={"item_ids": ["chk_hash"], "state": "complete"},
        )
        assert client.get(f"/roadmaps/{roadmap_id}/next").json()["complete"] is True

        # detailed snapshot persisted across the request cycle
        snapshot = client.get(f"/roadmaps/{roadmap_id}/progress", params={"detailed": True}).json()
        assert snapshot["percent"] == 100
        assert sorted(snapshot["checked_ids"]) == ["chk_drill", "chk_hash", "chk_read"]

        # deadline set -> echoed on the snapshot; a past date is allowed; clear it
        assert (
            client.put(f"/roadmaps/{roadmap_id}/deadline", json={"deadline": "2000-01-01"}).json()[
                "deadline"
            ]
            == "2000-01-01"
        )
        assert client.get(f"/roadmaps/{roadmap_id}/progress").json()["deadline"] == "2000-01-01"
        assert (
            client.put(f"/roadmaps/{roadmap_id}/deadline", json={"deadline": None}).json()[
                "deadline"
            ]
            is None
        )

        # a second user's progress is empty (per-user scoping), and they can read
        # the public published roadmap (a private one would 404 to a non-owner)
        client.cookies.clear()
        _register(client, "progother", "prog-other@example.com")
        other_snapshot = client.get(
            f"/roadmaps/{roadmap_id}/progress", params={"detailed": True}
        ).json()
        assert other_snapshot["checked_items"] == 0
        assert other_snapshot["checked_ids"] == []
        # and following it creates their own independent record
        assert client.post(f"/roadmaps/{roadmap_id}/follow").status_code == 201


def test_following_a_draft_is_a_409_end_to_end(
    migrated_url: str, make_settings: MakeSettings
) -> None:
    app = _external_app(migrated_url, make_settings(database_url=migrated_url))
    with TestClient(app) as client:
        _register(client, "progdraft", "prog-draft@example.com")
        # Created but never published: following it is a 409 (not startable).
        roadmap_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]
        blocked = client.post(f"/roadmaps/{roadmap_id}/follow")
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "CONFLICT"
