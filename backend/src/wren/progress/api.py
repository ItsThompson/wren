"""External REST adapter for progress: follow, snapshot, explicit-set, next.

Thin handlers (spec sections 05/06): each resolves the caller via ``require_user``
(the cookie session; a spoofed ``X-User-ID`` is stripped upstream), calls one
:class:`ProgressService` method, and lets the shared exception handler render any
``WrenError`` as RFC 9457 problem+json. The service is injected via
``service_provider`` so production binds a request-scoped DB session while tests
substitute an in-memory-backed service.

These routes hang under the ``/roadmaps/{id}`` resource (follow / progress / next)
and are all owner-or-follower reads/writes scoped to the resolved user.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends

from wren.core.identity import require_user
from wren.progress.schemas import (
    NextResult,
    Progress,
    ProgressSnapshot,
    ProgressUpdateRequest,
    ProgressUpdateResult,
)
from wren.progress.service import ProgressService
from wren.roadmaps.config import ROADMAPS_PATH

# A FastAPI dependency that yields a ProgressService for the request.
ProgressServiceProvider = Callable[..., object]


def create_progress_router(service_provider: ProgressServiceProvider) -> APIRouter:
    """Build the external progress router, injecting the service provider."""
    router = APIRouter(prefix=ROADMAPS_PATH, tags=["progress"])

    @router.post("/{roadmap_id}/follow", status_code=201)
    async def follow_roadmap(
        roadmap_id: str,
        user_id: str = Depends(require_user),
        service: ProgressService = Depends(service_provider),
    ) -> Progress:
        return await service.follow(user_id, roadmap_id)

    @router.get("/{roadmap_id}/progress")
    async def get_progress(
        roadmap_id: str,
        detailed: bool = False,
        user_id: str = Depends(require_user),
        service: ProgressService = Depends(service_provider),
    ) -> ProgressSnapshot:
        return await service.get(user_id, roadmap_id, detailed)

    @router.post("/{roadmap_id}/progress")
    async def update_progress(
        roadmap_id: str,
        body: ProgressUpdateRequest,
        user_id: str = Depends(require_user),
        service: ProgressService = Depends(service_provider),
    ) -> ProgressUpdateResult:
        return await service.update(user_id, roadmap_id, body.item_ids, body.state)

    @router.get("/{roadmap_id}/next")
    async def get_next(
        roadmap_id: str,
        user_id: str = Depends(require_user),
        service: ProgressService = Depends(service_provider),
    ) -> NextResult:
        return await service.get_next(user_id, roadmap_id)

    return router
