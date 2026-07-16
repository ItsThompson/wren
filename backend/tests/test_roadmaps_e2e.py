"""End-to-end runtime check: the assembled external app over real Postgres.

Boots an external-shaped app with the production wiring (request-scoped
SQLAlchemy repositories via ``get_session``, the real session verifier) against a
migrated ``postgres:17-alpine`` and drives the full HTTP cycle: register ->
create draft -> read own draft, and a second user's read is a 404. This proves
the create/read path works at runtime end to end, not only in unit isolation.
Skipped automatically when Docker is unavailable.
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

from tests.support.fakes.accounts_fakes import build_test_codec, build_test_hasher
from wren.accounts.api import create_accounts_router
from wren.accounts.config import CookieConfig
from wren.accounts.session import build_revocation_lookup, create_session_verifier
from wren.accounts.wiring import build_account_service_provider
from wren.core.app_factory import create_app
from wren.core.db import create_database
from wren.core.errors import build_exception_handlers
from wren.core.identity import StripInboundIdentityMiddleware, require_user
from wren.core.settings import AppSettings
from wren.progress.router import create_progress_router
from wren.progress.wiring import build_progress_service_provider
from wren.roadmaps.listing_api import create_listing_router
from wren.roadmaps.router import create_roadmaps_router
from wren.roadmaps.wiring import (
    build_listing_service_provider,
    build_roadmap_read_service_provider,
    build_roadmap_service_provider,
)

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
_PASSWORD = "Str0ngPass"
MakeSettings = Callable[..., AppSettings]

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

_PUBLISHABLE_ROADMAP = {
    "title": "Grokking DSA",
    "suggested_path": ["sub_arrays"],
    "sections": [
        {
            "title": "Foundations",
            "subsections": [
                {
                    "proposed_id": "sub_arrays",
                    "title": "Arrays",
                    "resources": [{"title": "Guide", "url": "https://x.test", "type": "article"}],
                    "checklist_items": [{"text": "Read it"}],
                }
            ],
        }
    ],
}

_REPLACE_ROADMAP = {
    "title": "Grokking DSA v2",
    "suggested_path": ["sub_arrays", "sub_graphs"],
    "sections": [
        {
            "proposed_id": "sec_core",
            "title": "Core",
            "subsections": [
                {
                    "proposed_id": "sub_arrays",
                    "title": "Arrays",
                    "resources": [{"title": "Guide", "url": "https://x.test", "type": "article"}],
                    "checklist_items": [{"text": "Read it"}],
                },
                {
                    "title": "Graphs",
                    "prereq_ids": ["sub_arrays"],
                    "resources": [{"title": "G", "url": "https://x.test", "type": "article"}],
                    "checklist_items": [{"text": "Do it"}],
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
        command.upgrade(config, "head")  # idempotent if another suite already ran it
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
        build_roadmap_service_provider(),
        build_roadmap_read_service_provider(),
        identity=require_user,
        include_web_lifecycle=True,
    )
    progress_router = create_progress_router(
        build_progress_service_provider(), identity=require_user
    )
    listing_router = create_listing_router(build_listing_service_provider())
    app = create_app(
        settings,
        routers=[accounts_router, roadmaps_router, progress_router, listing_router],
        exception_handlers=build_exception_handlers(),
    )
    app.state.db = database
    app.state.session_verifier = create_session_verifier(codec, build_revocation_lookup(database))
    app.add_middleware(StripInboundIdentityMiddleware)
    return app


def test_create_and_read_draft_end_to_end_over_http(
    migrated_url: str, make_settings: MakeSettings
) -> None:
    app = _external_app(migrated_url, make_settings(database_url=migrated_url))
    with TestClient(app) as client:
        register = client.post(
            "/auth/register",
            json={
                "username": "e2eauthor",
                "email": "e2e-author@example.com",
                "password": _PASSWORD,
            },
        )
        assert register.status_code == 201, register.text

        created = client.post("/roadmaps", json=_MINIMAL_ROADMAP)
        assert created.status_code == 201, created.text
        roadmap_id = created.json()["id"]
        assert roadmap_id.startswith("grokking-dsa-")

        fetched = client.get(f"/roadmaps/{roadmap_id}")
        assert fetched.status_code == 200
        assert "sub_arrays" in fetched.json()["sections"]["sec_foundations"]["subsections"]

        # A different user cannot reach the draft (owner-scoped; no existence leak).
        client.cookies.clear()
        client.post(
            "/auth/register",
            json={
                "username": "e2eother",
                "email": "e2e-other@example.com",
                "password": _PASSWORD,
            },
        )
        denied = client.get(f"/roadmaps/{roadmap_id}")
        assert denied.status_code == 404


def test_validate_and_publish_transition_end_to_end_over_http(
    migrated_url: str, make_settings: MakeSettings
) -> None:
    app = _external_app(migrated_url, make_settings(database_url=migrated_url))
    with TestClient(app) as client:
        register = client.post(
            "/auth/register",
            json={
                "username": "e2epublisher",
                "email": "e2e-publisher@example.com",
                "password": _PASSWORD,
            },
        )
        assert register.status_code == 201, register.text

        roadmap_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]

        # Validate is clean for a publishable draft, and never mutates.
        validated = client.post(f"/roadmaps/{roadmap_id}:validate")
        assert validated.status_code == 200, validated.text
        assert validated.json() == {"violations": []}
        assert client.get(f"/roadmaps/{roadmap_id}").json()["status"] == "draft"

        # Publish transitions to published and persists to Postgres.
        published = client.post(f"/roadmaps/{roadmap_id}:publish")
        assert published.status_code == 200, published.text
        assert published.json()["status"] == "published"
        assert client.get(f"/roadmaps/{roadmap_id}").json()["status"] == "published"

        # One-way: republishing an already-published roadmap is a 409.
        assert client.post(f"/roadmaps/{roadmap_id}:publish").status_code == 409


def test_publish_hard_block_end_to_end_over_http(
    migrated_url: str, make_settings: MakeSettings
) -> None:
    app = _external_app(migrated_url, make_settings(database_url=migrated_url))
    with TestClient(app) as client:
        client.post(
            "/auth/register",
            json={
                "username": "e2eblocked",
                "email": "e2e-blocked@example.com",
                "password": _PASSWORD,
            },
        )
        # No suggested_path: the minimal validator hard-blocks publish.
        roadmap_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]
        blocked = client.post(f"/roadmaps/{roadmap_id}:publish")
        assert blocked.status_code == 422, blocked.text
        assert [v["rule"] for v in blocked.json()["violations"]] == ["V3_PATH_COVERAGE"]
        # The draft is untouched.
        assert client.get(f"/roadmaps/{roadmap_id}").json()["status"] == "draft"


def test_patch_draft_end_to_end_over_http(migrated_url: str, make_settings: MakeSettings) -> None:
    app = _external_app(migrated_url, make_settings(database_url=migrated_url))
    with TestClient(app) as client:
        register = client.post(
            "/auth/register",
            json={
                "username": "e2epatcher",
                "email": "e2e-patcher@example.com",
                "password": _PASSWORD,
            },
        )
        assert register.status_code == 201, register.text

        roadmap_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]

        # An atomic op batch under If-Match: applies, bumps the revision, and
        # persists to Postgres.
        patched = client.patch(
            f"/roadmaps/{roadmap_id}",
            headers={"If-Match": "1"},
            json={
                "operations": [
                    {"op": "set_tags", "subsection_id": "sub_arrays", "tags": ["core"]},
                    {
                        "op": "add_item",
                        "subsection_id": "sub_arrays",
                        "text": "Practice",
                        "proposed_id": "chk_practice",
                    },
                ]
            },
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["revision"] == 2

        fetched = client.get(f"/roadmaps/{roadmap_id}").json()
        assert fetched["revision"] == 2
        arrays = fetched["sections"]["sec_foundations"]["subsections"]["sub_arrays"]
        assert arrays["tags"] == ["core"]
        assert "chk_practice" in arrays["checklist_items"]

        # Re-using the now-stale revision 1 is a 409 "re-read".
        stale = client.patch(
            f"/roadmaps/{roadmap_id}",
            headers={"If-Match": "1"},
            json={"operations": [{"op": "set_tags", "subsection_id": "sub_arrays", "tags": []}]},
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "STALE_REVISION"


def test_replace_import_and_immutability_end_to_end_over_http(
    migrated_url: str, make_settings: MakeSettings
) -> None:
    app = _external_app(migrated_url, make_settings(database_url=migrated_url))
    with TestClient(app) as client:
        register = client.post(
            "/auth/register",
            json={
                "username": "e2eimporter",
                "email": "e2e-importer@example.com",
                "password": _PASSWORD,
            },
        )
        assert register.status_code == 201, register.text

        roadmap_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]

        # PUT replaces the entire draft under If-Match: the roadmap ID is unchanged,
        # proposed_ids are preserved, the rest re-minted, and the revision bumps.
        replaced = client.put(
            f"/roadmaps/{roadmap_id}", headers={"If-Match": "1"}, json=_REPLACE_ROADMAP
        )
        assert replaced.status_code == 200, replaced.text
        body = replaced.json()
        assert body["id"] == roadmap_id
        assert body["revision"] == 2
        assert body["sections"]["sec_core"]["subsection_order"] == ["sub_arrays", "sub_graphs"]

        # Publish, then a structural write (PUT import) is refused: published content
        # is immutable (409 IMMUTABLE, fork-to-change).
        assert client.post(f"/roadmaps/{roadmap_id}:publish").status_code == 200
        immutable = client.put(
            f"/roadmaps/{roadmap_id}", headers={"If-Match": "2"}, json=_REPLACE_ROADMAP
        )
        assert immutable.status_code == 409
        assert immutable.json()["code"] == "IMMUTABLE"


def test_fork_with_fresh_progress_end_to_end_over_http(
    migrated_url: str, make_settings: MakeSettings
) -> None:
    app = _external_app(migrated_url, make_settings(database_url=migrated_url))
    with TestClient(app) as client:
        register = client.post(
            "/auth/register",
            json={
                "username": "e2eforker",
                "email": "e2e-forker@example.com",
                "password": _PASSWORD,
            },
        )
        assert register.status_code == 201, register.text

        source_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]
        assert client.post(f"/roadmaps/{source_id}:publish").status_code == 200

        # The author checks an item on the source (source progress = 1 checked).
        item_id = client.get(f"/roadmaps/{source_id}").json()["sections"]["sec_foundations"][
            "subsections"
        ]["sub_arrays"]["item_order"][0]
        checked = client.post(
            f"/roadmaps/{source_id}/progress",
            json={"item_ids": [item_id], "state": "complete"},
        )
        assert checked.status_code == 200, checked.text

        # Fork the (owned, published) roadmap: a fresh draft with a new ID.
        fork = client.post(f"/roadmaps/{source_id}:fork")
        assert fork.status_code == 201, fork.text
        fork_id = fork.json()["id"]
        assert fork_id != source_id
        # The fork copied the same item ID verbatim.
        assert (
            item_id
            in fork.json()["sections"]["sec_foundations"]["subsections"]["sub_arrays"][
                "checklist_items"
            ]
        )

        # Publish the fork, then its progress is empty: no carry-over across the fork.
        assert client.post(f"/roadmaps/{fork_id}:publish").status_code == 200
        fork_progress = client.get(f"/roadmaps/{fork_id}/progress?detailed=true").json()
        assert fork_progress["checked_items"] == 0
        # The source progress is untouched (still one item checked).
        source_progress = client.get(f"/roadmaps/{source_id}/progress?detailed=true").json()
        assert source_progress["checked_items"] == 1


def test_edit_metadata_on_published_end_to_end_over_http(
    migrated_url: str, make_settings: MakeSettings
) -> None:
    app = _external_app(migrated_url, make_settings(database_url=migrated_url))
    with TestClient(app) as client:
        register = client.post(
            "/auth/register",
            json={
                "username": "e2emeta",
                "email": "e2e-meta@example.com",
                "password": _PASSWORD,
            },
        )
        assert register.status_code == 201, register.text

        roadmap_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]
        assert client.post(f"/roadmaps/{roadmap_id}:publish").status_code == 200

        # A structural write is refused on published content...
        structural = client.patch(
            f"/roadmaps/{roadmap_id}",
            headers={"If-Match": "1"},
            json={"operations": [{"op": "set_tags", "subsection_id": "sub_arrays", "tags": ["x"]}]},
        )
        assert structural.status_code == 409
        assert structural.json()["code"] == "IMMUTABLE"

        # ...while the presentation-only metadata edit succeeds and persists,
        # without bumping the structural revision.
        edited = client.patch(
            f"/roadmaps/{roadmap_id}/metadata",
            json={"title": "Renamed live", "subject_tags": ["cs"]},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["title"] == "Renamed live"
        fetched = client.get(f"/roadmaps/{roadmap_id}").json()
        assert fetched["title"] == "Renamed live"
        assert fetched["subject_tags"] == ["cs"]
        assert fetched["status"] == "published"
        assert fetched["revision"] == 1


def test_visibility_toggle_end_to_end_over_http(
    migrated_url: str, make_settings: MakeSettings
) -> None:
    app = _external_app(migrated_url, make_settings(database_url=migrated_url))
    with TestClient(app) as client:
        register = client.post(
            "/auth/register",
            json={
                "username": "e2evis",
                "email": "e2e-vis@example.com",
                "password": _PASSWORD,
            },
        )
        assert register.status_code == 201, register.text
        roadmap_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]
        assert client.get(f"/roadmaps/{roadmap_id}").json()["visibility"] == "private"

        made_public = client.put(
            f"/roadmaps/{roadmap_id}/visibility", json={"visibility": "public"}
        )
        assert made_public.status_code == 200, made_public.text
        assert made_public.json()["visibility"] == "public"
        # Persisted, and the structural revision is untouched by the toggle.
        fetched = client.get(f"/roadmaps/{roadmap_id}").json()
        assert fetched["visibility"] == "public"
        assert fetched["revision"] == 1


def test_delete_zero_followers_end_to_end_over_http(
    migrated_url: str, make_settings: MakeSettings
) -> None:
    app = _external_app(migrated_url, make_settings(database_url=migrated_url))
    with TestClient(app) as client:
        register = client.post(
            "/auth/register",
            json={
                "username": "e2edel",
                "email": "e2e-del@example.com",
                "password": _PASSWORD,
            },
        )
        assert register.status_code == 201, register.text
        roadmap_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]

        # Zero followers: delete succeeds (204) and the row is gone from Postgres.
        deleted = client.delete(f"/roadmaps/{roadmap_id}")
        assert deleted.status_code == 204, deleted.text
        assert client.get(f"/roadmaps/{roadmap_id}").status_code == 404


def test_delete_blocked_by_followers_then_archive_keeps_follower_end_to_end_over_http(
    migrated_url: str, make_settings: MakeSettings
) -> None:
    # The gold web-only-lifecycle proof over real Postgres: a followed roadmap
    # cannot be deleted (real follower-count guard), archive is the retirement
    # path, and the existing follower keeps reading their progress on the archived
    # roadmap.
    app = _external_app(migrated_url, make_settings(database_url=migrated_url))
    with TestClient(app) as client:
        # Owner publishes and makes the roadmap public so a follower can reach it.
        assert (
            client.post(
                "/auth/register",
                json={
                    "username": "e2eowner15",
                    "email": "e2e-owner15@example.com",
                    "password": _PASSWORD,
                },
            ).status_code
            == 201
        )
        roadmap_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]
        assert client.post(f"/roadmaps/{roadmap_id}:publish").status_code == 200
        assert (
            client.put(
                f"/roadmaps/{roadmap_id}/visibility", json={"visibility": "public"}
            ).status_code
            == 200
        )

        # A second user follows it and records some progress.
        client.cookies.clear()
        assert (
            client.post(
                "/auth/register",
                json={
                    "username": "e2efollower15",
                    "email": "e2e-follower15@example.com",
                    "password": _PASSWORD,
                },
            ).status_code
            == 201
        )
        assert client.post(f"/roadmaps/{roadmap_id}/follow").status_code == 201
        item_id = client.get(f"/roadmaps/{roadmap_id}").json()["sections"]["sec_foundations"][
            "subsections"
        ]["sub_arrays"]["item_order"][0]
        assert (
            client.post(
                f"/roadmaps/{roadmap_id}/progress",
                json={"item_ids": [item_id], "state": "complete"},
            ).status_code
            == 200
        )

        # The owner logs back in: delete is refused (real follower present), archive
        # succeeds.
        client.cookies.clear()
        assert (
            client.post(
                "/auth/login",
                json={"email": "e2e-owner15@example.com", "password": _PASSWORD},
            ).status_code
            == 200
        )
        blocked = client.delete(f"/roadmaps/{roadmap_id}")
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["code"] == "DELETE_HAS_FOLLOWERS"
        archived = client.post(f"/roadmaps/{roadmap_id}:archive")
        assert archived.status_code == 200, archived.text
        assert archived.json()["status"] == "archived"

        # The follower still keeps their progress on the archived roadmap.
        client.cookies.clear()
        assert (
            client.post(
                "/auth/login",
                json={"email": "e2e-follower15@example.com", "password": _PASSWORD},
            ).status_code
            == 200
        )
        progress = client.get(f"/roadmaps/{roadmap_id}/progress?detailed=true")
        assert progress.status_code == 200, progress.text
        assert progress.json()["checked_items"] == 1


def test_dashboard_and_profile_end_to_end_over_http(
    migrated_url: str, make_settings: MakeSettings
) -> None:
    # Drives the real list queries (list_owned / list_published_public /
    # list_by_ids / list_followed_roadmap_ids + the handle resolver) against
    # Postgres: the owner's dashboard shows their authored roadmaps at every
    # status plus what they follow, and the public profile shows only their
    # published-public roadmap.
    app = _external_app(migrated_url, make_settings(database_url=migrated_url))
    with TestClient(app) as client:
        assert (
            client.post(
                "/auth/register",
                json={
                    "username": "e2edash",
                    "email": "e2e-dash@example.com",
                    "password": _PASSWORD,
                },
            ).status_code
            == 201
        )
        # A private draft (stays private) and a second roadmap published + public.
        draft_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]
        public_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]
        assert client.post(f"/roadmaps/{public_id}:publish").status_code == 200
        assert (
            client.put(
                f"/roadmaps/{public_id}/visibility", json={"visibility": "public"}
            ).status_code
            == 200
        )

        # The owner's dashboard: both authored (any status), nothing followed yet.
        dashboard = client.get("/me/dashboard").json()
        assert {card["id"] for card in dashboard["authored"]} == {draft_id, public_id}
        assert dashboard["followed"] == []

        # The public profile lists only the published-public roadmap (the private
        # draft never appears), and is reachable without a session.
        client.cookies.clear()
        profile = client.get("/users/e2edash")
        assert profile.status_code == 200, profile.text
        assert [card["id"] for card in profile.json()["roadmaps"]] == [public_id]
        assert client.get("/users/nobody-here").status_code == 404

        # A follower's dashboard surfaces the followed roadmap.
        assert (
            client.post(
                "/auth/register",
                json={
                    "username": "e2edashfollower",
                    "email": "e2e-dashfollower@example.com",
                    "password": _PASSWORD,
                },
            ).status_code
            == 201
        )
        assert client.post(f"/roadmaps/{public_id}/follow").status_code == 201
        follower_dashboard = client.get("/me/dashboard").json()
        assert follower_dashboard["authored"] == []
        assert [card["id"] for card in follower_dashboard["followed"]] == [public_id]
