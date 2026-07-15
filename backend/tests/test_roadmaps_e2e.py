"""End-to-end runtime check: the assembled external app over real Postgres.

Boots an external-shaped app with the production wiring (request-scoped
SQLAlchemy repositories via ``get_session``, the real session verifier) against a
migrated ``postgres:17-alpine`` and drives the full HTTP cycle: register ->
create draft -> read own draft, and a second user's read is a 404. This proves
the create/read path works at runtime end to end, not only in unit isolation
(spec section 13). Skipped automatically when Docker is unavailable.
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
from wren.roadmaps.api import create_roadmaps_router
from wren.roadmaps.wiring import build_roadmap_service_provider

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
    roadmaps_router = create_roadmaps_router(build_roadmap_service_provider())
    app = create_app(
        settings,
        routers=[accounts_router, roadmaps_router],
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
