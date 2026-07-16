"""Internal app entrypoint (:8001).

Never tunnel-routed and never host-published: reachable only by containers on
``compute-net`` (i.e. the MCP server). Trusts the ``X-User-ID`` header. Built from
the shared factory with the internal service identity injected, differing from the
external app only by these settings.

Mounts the roadmap + progress routers as thin adapters over the same service
layer the external app uses (:mod:`wren.roadmaps.router`,
:mod:`wren.progress.router`), differing only in that ``identity`` resolves the
trusted ``X-User-ID`` header (``require_internal_user``) instead of the cookie and
the web-only lifecycle routes are never mounted. These are the endpoints the MCP
write/read tools call, one HTTP call per tool.
"""

from __future__ import annotations

from fastapi import FastAPI

from wren.core.app_factory import create_app
from wren.core.db import create_database, create_db_lifespan, db_readiness_check
from wren.core.errors import build_exception_handlers
from wren.core.identity import require_internal_user
from wren.core.settings import INTERNAL_PORT, INTERNAL_SERVICE, build_app_settings
from wren.progress.router import create_progress_router
from wren.progress.wiring import build_progress_service_provider
from wren.roadmaps.router import create_roadmaps_router
from wren.roadmaps.wiring import (
    build_roadmap_read_service_provider,
    build_roadmap_service_provider,
)

settings = build_app_settings(service=INTERNAL_SERVICE, port=INTERNAL_PORT)
db = create_database(settings.database_url)

# Roadmap authoring/reading over the trusted identity: the same factories the
# external app binds, differing only in that require_internal_user resolves the
# user from the trusted X-User-ID header and include_web_lifecycle stays False, so
# the web-only visibility / archive / delete routes are never mounted here.
internal_roadmaps_router = create_roadmaps_router(
    build_roadmap_service_provider(),
    build_roadmap_read_service_provider(),
    identity=require_internal_user,
)

# Progress surface over the trusted identity: follow / snapshot /
# explicit-set / next, the endpoints the MCP progress tools call.
internal_progress_router = create_progress_router(
    build_progress_service_provider(), identity=require_internal_user
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
