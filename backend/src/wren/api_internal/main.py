"""Internal app entrypoint (:8001).

Never tunnel-routed and never host-published: reachable in-network by first-party
``app-net`` containers and gated by the shared ``INTERNAL_API_TOKEN`` (the MCP
server is its intended caller). Trusts the ``X-User-ID`` header. Built from
the shared factory with the internal service identity injected, differing from the
external app only by these settings.

Mounts the roadmap + progress routers as thin adapters over the same service
layer the external app uses (:mod:`wren.roadmaps.router`,
:mod:`wren.progress.router`), passing ``App.INTERNAL``. The registry drives both
which routes mount (only those an MCP tool consumes) and the identity each
resolves (the trusted ``X-User-ID`` header, ``require_internal_user``). The
web-only lifecycle and follow/deadline routes are declared for the external app
only, so they are never built here. These are the endpoints the MCP write/read
tools call, one HTTP call per tool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wren.core.app_factory import create_app
from wren.core.db import create_database, create_db_lifespan, db_readiness_check
from wren.core.errors import build_exception_handlers
from wren.core.route_registry import App
from wren.core.settings import INTERNAL_PORT, INTERNAL_SERVICE, build_app_settings
from wren.progress.router import create_progress_router
from wren.progress.wiring import build_progress_service_provider
from wren.roadmaps.router import create_roadmaps_router
from wren.roadmaps.wiring import (
    build_roadmap_read_service_provider,
    build_roadmap_service_provider,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

settings = build_app_settings(service=INTERNAL_SERVICE, port=INTERNAL_PORT)
db = create_database(settings.database_url)

# Roadmap authoring/reading over the trusted identity: the same factory the
# external app binds, passing App.INTERNAL so the registry resolves
# require_internal_user and mounts only the routes an MCP tool consumes (the
# web-only visibility / archive / delete routes are external-only, never built here).
internal_roadmaps_router = create_roadmaps_router(
    build_roadmap_service_provider(),
    build_roadmap_read_service_provider(),
    app=App.INTERNAL,
)

# Progress surface over the trusted identity: snapshot / explicit-set / next, the
# three endpoints the MCP progress tools call. The web-only follow / deadline
# routes are external-only, so App.INTERNAL never mounts them.
internal_progress_router = create_progress_router(
    build_progress_service_provider(), app=App.INTERNAL
)

app: FastAPI = create_app(
    settings,
    routers=[internal_roadmaps_router, internal_progress_router],
    readiness_checks=[db_readiness_check(db.engine)],
    exception_handlers=build_exception_handlers(),
    lifespan=create_db_lifespan(db.engine),
)
app.state.db = db
# The internal app trusts X-User-ID behind this shared token (require_internal_user).
app.state.internal_api_token = settings.internal_api_token


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run("wren.api_internal.main:app", host=settings.host, port=settings.port)
