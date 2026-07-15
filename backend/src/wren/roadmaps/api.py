"""External REST adapter for roadmaps: create, read, iterative-edit (patch),
full-document import (replace), validate, and publish.

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

from fastapi import APIRouter, Depends, Header

from wren.core.identity import require_user
from wren.roadmaps.config import ROADMAPS_PATH
from wren.roadmaps.schemas import (
    PatchRequest,
    PatchResult,
    Roadmap,
    RoadmapCreated,
    RoadmapInput,
    RoadmapReplaced,
    ValidateResult,
)
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

    @router.patch("/{roadmap_id}")
    async def patch_roadmap(
        roadmap_id: str,
        body: PatchRequest,
        if_match: int = Header(alias="If-Match"),
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> PatchResult:
        # If-Match carries the target revision (spec section 06): a mismatch is a
        # 409 "re-read", an invalid op is a 422, both rendered by the shared
        # exception handler. A malformed/absent header is a 422 via FastAPI.
        return await service.patch_draft(user_id, roadmap_id, if_match, body.operations)

    @router.put("/{roadmap_id}")
    async def replace_roadmap(
        roadmap_id: str,
        body: RoadmapInput,
        if_match: int = Header(alias="If-Match"),
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> RoadmapReplaced:
        # The full-document import escape hatch (spec section 07), never the
        # iterative path: it replaces the entire draft. Guarded by the same If-Match
        # optimistic concurrency as PATCH (stale -> 409) and the same immutability
        # boundary (published/archived -> 409 IMMUTABLE), rendered by the shared
        # exception handler.
        return await service.replace_draft(user_id, roadmap_id, if_match, body)

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
