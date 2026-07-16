"""Contract tests for GET /skill.

Asserts the shipped SKILL.md authoring guidance is served over real HTTP as
UTF-8 Markdown, needs no session (it is PUBLIC guidance, not user data), and that
its access level is declared PUBLIC in the route registry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from wren.core.app_factory import create_app
from wren.core.route_registry import EXTERNAL_ROUTE_ACCESS, AccessLevel, RouteKey
from wren.core.settings import AppSettings
from wren.skill.api import create_skill_router
from wren.skill.content import read_skill_markdown

if TYPE_CHECKING:
    from fastapi import FastAPI

MakeSettings = Callable[..., AppSettings]


def _client(make_settings: MakeSettings) -> TestClient:
    app: FastAPI = create_app(make_settings(), routers=[create_skill_router()])
    return TestClient(app)


def test_get_skill_serves_the_markdown_guidance(make_settings: MakeSettings) -> None:
    response = _client(make_settings).get("/skill")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    # Byte-for-byte the shipped guidance (no truncation / re-encoding).
    assert response.text == read_skill_markdown()


def test_get_skill_needs_no_session(make_settings: MakeSettings) -> None:
    # No cookie, no bearer: an unauthenticated agent must be able to fetch it.
    response = _client(make_settings).get("/skill")
    assert response.status_code == 200
    assert "suggested_path" in response.text


def test_skill_route_is_declared_public() -> None:
    assert EXTERNAL_ROUTE_ACCESS[RouteKey(method="GET", path="/skill")] is AccessLevel.PUBLIC
