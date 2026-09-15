"""Verify MCP discovery reads against the real internal ASGI routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from pydantic import SecretStr
from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.route_registry import App
from wren.core.settings import EnvSettings, build_app_settings
from wren.roadmaps.list_schemas import Dashboard, Profile
from wren.roadmaps.listing_api import create_listing_router
from wren.roadmaps.router import create_roadmaps_router
from wren_mcp.client import InternalApiClient

if TYPE_CHECKING:
    from fastapi import FastAPI

_INTERNAL_TOKEN = "contract-internal-token"
_USER_ID = "user-ada"
_ROADMAP_ID = "roadmap-contract"


def _roadmap_body() -> dict[str, Any]:
    return {
        "id": _ROADMAP_ID,
        "owner": _USER_ID,
        "title": "Contract roadmap",
        "description": "A populated canonical document.",
        "subject_tags": ["python", "databases"],
        "published_visibility": "public",
        "status": "published",
        "revision": 7,
        "sections": {
            "sec_core": {
                "id": "sec_core",
                "title": "Core",
                "subsection_order": ["sub_sql"],
                "subsections": {
                    "sub_sql": {
                        "id": "sub_sql",
                        "title": "SQL",
                        "description": "Query fundamentals.",
                        "tags": ["data"],
                        "effort_estimate": None,
                        "resources": {
                            "res_guide": {
                                "id": "res_guide",
                                "title": "Guide",
                                "url": "https://example.test/sql",
                                "type": "article",
                            }
                        },
                        "resource_order": ["res_guide"],
                        "checklist_items": {
                            "chk_read": {"id": "chk_read", "text": "Read the guide"}
                        },
                        "item_order": ["chk_read"],
                        "prereq_ids": [],
                    }
                },
            }
        },
        "section_order": ["sec_core"],
        "suggested_path": ["sub_sql"],
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-02T00:00:00Z",
    }


class _ListingService:
    def __init__(self) -> None:
        self.dashboard_users: list[str] = []
        self.profile_handles: list[str] = []

    async def dashboard(self, user_id: str) -> Dashboard:
        self.dashboard_users.append(user_id)
        return Dashboard.model_validate({"authored": [], "followed": []})

    async def profile(self, handle: str) -> Profile:
        self.profile_handles.append(handle)
        return Profile.model_validate({"handle": handle, "display_name": "Ada", "roadmaps": []})


class _ReadService:
    def __init__(self, roadmap: dict[str, Any]) -> None:
        self.roadmap = roadmap
        self.users: list[str] = []
        self.roadmap_ids: list[str] = []

    async def get(self, user_id: str, roadmap_id: str) -> Any:
        self.users.append(user_id)
        self.roadmap_ids.append(roadmap_id)
        return self.roadmap


def _app() -> tuple[FastAPI, _ListingService, _ReadService]:
    listing = _ListingService()
    read = _ReadService(_roadmap_body())
    settings = build_app_settings(
        service="contract-internal",
        port=8001,
        env=EnvSettings(
            environment="test",
            internal_api_token=SecretStr(_INTERNAL_TOKEN),
        ),
    )
    app = create_app(
        settings,
        routers=[
            create_roadmaps_router(lambda: object(), lambda: read, app=App.INTERNAL),
            create_listing_router(lambda: listing, app=App.INTERNAL),
        ],
        exception_handlers=build_exception_handlers(),
    )
    app.state.internal_api_token = SecretStr(_INTERNAL_TOKEN)
    return app, listing, read


@pytest.mark.asyncio
async def test_discovery_reads_cross_the_internal_app_with_complete_roadmap() -> None:
    app, listing, read = _app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://internal.test"
    ) as http:
        client = InternalApiClient(http, api_token=SecretStr(_INTERNAL_TOKEN))
        dashboard = await client.list_roadmaps(_USER_ID)
        profile = await client.get_profile(_USER_ID, "ada")
        roadmap = await client.get_roadmap(_USER_ID, _ROADMAP_ID)

    assert dashboard.status_code == 200  # noqa: S101
    assert profile.status_code == 200  # noqa: S101
    assert roadmap.status_code == 200  # noqa: S101
    assert roadmap.json() == _roadmap_body()  # noqa: S101
    assert listing.dashboard_users == [_USER_ID]  # noqa: S101
    assert listing.profile_handles == ["ada"]  # noqa: S101
    assert read.users == [_USER_ID]  # noqa: S101
    assert read.roadmap_ids == [_ROADMAP_ID]  # noqa: S101
