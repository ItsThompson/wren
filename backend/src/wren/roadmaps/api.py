"""External REST adapter for roadmaps: create, read, validate, and publish.

Thin handlers (spec sections 05/06): each resolves the caller via ``require_user``
(the cookie session; a spoofed ``X-User-ID`` is stripped upstream), calls one
:class:`RoadmapService` method, and lets the shared exception handler render any
``WrenError`` as RFC 9457 problem+json. The service is injected via
``service_provider`` so production binds a request-scoped DB session while tests
substitute an in-memory-backed service.

The lifecycle commands use the ``:verb`` action sub-resource form
(``POST /roadmaps/{id}:validate`` / ``:publish``); ``publish`` hard-blocks with a
422 carrying the ``Violation`` list, while ``validate`` always returns 200 with a
(possibly empty) list.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends

from wren.core.identity import require_user
from wren.roadmaps.config import ROADMAPS_PATH
from wren.roadmaps.schemas import Roadmap, RoadmapCreated, RoadmapInput, ValidateResult
from wren.roadmaps.service import RoadmapService

# A FastAPI dependency that yields a RoadmapService for the request.
RoadmapServiceProvider = Callable[..., object]


def create_roadmaps_router(service_provider: RoadmapServiceProvider) -> APIRouter:
    """Build the /roadmaps router, injecting the service provider."""
    router = APIRouter(prefix=ROADMAPS_PATH, tags=["roadmaps"])

    @router.post("", status_code=201)
    async def create_roadmap(
        body: RoadmapInput,
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> RoadmapCreated:
        return await service.create_draft(user_id, body)

    @router.get("/{roadmap_id}")
    async def get_roadmap(
        roadmap_id: str,
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        return await service.get(user_id, roadmap_id)

    @router.post("/{roadmap_id}:validate")
    async def validate_roadmap(
        roadmap_id: str,
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> ValidateResult:
        violations = await service.validate(user_id, roadmap_id)
        return ValidateResult(violations=violations)

    @router.post("/{roadmap_id}:publish")
    async def publish_roadmap(
        roadmap_id: str,
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        return await service.publish(user_id, roadmap_id)

    return router
