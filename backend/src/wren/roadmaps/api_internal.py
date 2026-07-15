"""Internal REST adapter for roadmaps (:8001), the surface the MCP server calls.

Mirrors the external ``/roadmaps`` router (:mod:`wren.roadmaps.api`) op-for-op but
resolves the caller via :func:`require_internal_user` (the trusted ``X-User-ID``
header behind the shared ``INTERNAL_API_TOKEN``, spec section 08) instead of the
human session cookie. Both are thin adapters over the same :class:`RoadmapService`:
identical business rules, different identity resolution. The internal app is never
tunnel-routed or host-published (spec section 11), so it is reachable only by the
MCP server on ``compute-net``; the trusted identity is taken on trust here, never
re-validated.

The MCP write/read tools (Tickets 21/22) are thin clients of these endpoints: one
tool call becomes one internal HTTP call carrying the resolved ``X-User-ID``.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, Header

from wren.core.identity import require_internal_user
from wren.roadmaps.config import ROADMAPS_PATH
from wren.roadmaps.schemas import (
    PatchRequest,
    PatchResult,
    Roadmap,
    RoadmapCreated,
    RoadmapInput,
    ValidateResult,
)
from wren.roadmaps.service import RoadmapService

# A FastAPI dependency that yields a RoadmapService for the request.
RoadmapServiceProvider = Callable[..., object]


def create_internal_roadmaps_router(service_provider: RoadmapServiceProvider) -> APIRouter:
    """Build the internal /roadmaps router, injecting the service provider.

    Every handler resolves ``user_id`` from the trusted ``X-User-ID`` header (via
    :func:`require_internal_user`) and delegates to one service method; the service
    scopes every query to that user, so a tool can never reach another user's
    roadmap even though the internal app trusts the injected identity.
    """
    router = APIRouter(prefix=ROADMAPS_PATH, tags=["roadmaps-internal"])

    @router.post("", status_code=201)
    async def create_roadmap(
        body: RoadmapInput,
        user_id: str = Depends(require_internal_user),
        service: RoadmapService = Depends(service_provider),
    ) -> RoadmapCreated:
        return await service.create_draft(user_id, body)

    @router.get("/{roadmap_id}")
    async def get_roadmap(
        roadmap_id: str,
        user_id: str = Depends(require_internal_user),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        return await service.get(user_id, roadmap_id)

    @router.patch("/{roadmap_id}")
    async def patch_roadmap(
        roadmap_id: str,
        body: PatchRequest,
        if_match: int = Header(alias="If-Match"),
        user_id: str = Depends(require_internal_user),
        service: RoadmapService = Depends(service_provider),
    ) -> PatchResult:
        # If-Match carries the target revision (spec section 06): a mismatch is a
        # 409 "re-read", an invalid op is a 422, both rendered by the shared
        # exception handler. A malformed/absent header is a 422 via FastAPI.
        return await service.patch_draft(user_id, roadmap_id, if_match, body.operations)

    @router.post("/{roadmap_id}:validate")
    async def validate_roadmap(
        roadmap_id: str,
        user_id: str = Depends(require_internal_user),
        service: RoadmapService = Depends(service_provider),
    ) -> ValidateResult:
        violations = await service.validate(user_id, roadmap_id)
        return ValidateResult(violations=violations)

    @router.post("/{roadmap_id}:publish")
    async def publish_roadmap(
        roadmap_id: str,
        user_id: str = Depends(require_internal_user),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        return await service.publish(user_id, roadmap_id)

    return router
