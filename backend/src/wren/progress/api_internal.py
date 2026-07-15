"""Internal REST adapter for progress (:8001), the surface the MCP server calls.

Mirrors the external progress router (:mod:`wren.progress.api`) op-for-op but
resolves the caller via :func:`require_internal_user` (the trusted ``X-User-ID``
header behind the shared ``INTERNAL_API_TOKEN``, spec section 08) instead of the
human session cookie. Both are thin adapters over the same
:class:`ProgressService`: identical business rules, different identity
resolution. The internal app is never tunnel-routed or host-published (spec
section 11), so it is reachable only by the MCP server on ``compute-net``.

The MCP progress tools (Ticket 22: ``progress_get`` / ``progress_update``) are
thin clients of these endpoints: one tool call becomes one internal HTTP call
carrying the resolved ``X-User-ID``. Ticket 20 built the internal roadmaps
router and deferred these progress routers to this slice.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends

from wren.core.identity import require_internal_user
from wren.progress.schemas import (
    DeadlineRequest,
    NextResult,
    Progress,
    ProgressSnapshot,
    ProgressUpdateRequest,
    ProgressUpdateResult,
)
from wren.progress.service import ProgressService
from wren.roadmaps.config import ROADMAPS_PATH
from wren.roadmaps.read_schemas import ResponseFormat

# A FastAPI dependency that yields a ProgressService for the request.
ProgressServiceProvider = Callable[..., object]


def create_internal_progress_router(service_provider: ProgressServiceProvider) -> APIRouter:
    """Build the internal progress router, injecting the service provider.

    Every handler resolves ``user_id`` from the trusted ``X-User-ID`` header (via
    :func:`require_internal_user`) and delegates to one service method; the
    service scopes every query to that user, so a tool can never reach another
    user's progress even though the internal app trusts the injected identity.
    """
    router = APIRouter(prefix=ROADMAPS_PATH, tags=["progress-internal"])

    @router.post("/{roadmap_id}/follow", status_code=201)
    async def follow_roadmap(
        roadmap_id: str,
        user_id: str = Depends(require_internal_user),
        service: ProgressService = Depends(service_provider),
    ) -> Progress:
        return await service.follow(user_id, roadmap_id)

    @router.get("/{roadmap_id}/progress")
    async def get_progress(
        roadmap_id: str,
        detailed: bool = False,
        user_id: str = Depends(require_internal_user),
        service: ProgressService = Depends(service_provider),
    ) -> ProgressSnapshot:
        return await service.get(user_id, roadmap_id, detailed)

    @router.post("/{roadmap_id}/progress")
    async def update_progress(
        roadmap_id: str,
        body: ProgressUpdateRequest,
        user_id: str = Depends(require_internal_user),
        service: ProgressService = Depends(service_provider),
    ) -> ProgressUpdateResult:
        return await service.update(user_id, roadmap_id, body.item_ids, body.state)

    @router.get("/{roadmap_id}/next")
    async def get_next(
        roadmap_id: str,
        format: ResponseFormat = ResponseFormat.CONCISE,
        user_id: str = Depends(require_internal_user),
        service: ProgressService = Depends(service_provider),
    ) -> NextResult:
        # Mirrors the external next route for the MCP roadmap_get_next tool
        # (Ticket 22): server-computed items + structural why_now, path_position
        # under detailed.
        return await service.get_next(user_id, roadmap_id, format)

    @router.put("/{roadmap_id}/deadline")
    async def set_deadline(
        roadmap_id: str,
        body: DeadlineRequest,
        user_id: str = Depends(require_internal_user),
        service: ProgressService = Depends(service_provider),
    ) -> Progress:
        # Set/clear the per-user deadline over the trusted identity (countdown
        # only, no pacing); mirrors the external deadline route for Ticket 22.
        return await service.set_deadline(user_id, roadmap_id, body.deadline)

    return router
