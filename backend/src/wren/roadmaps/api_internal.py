"""Internal REST adapter for roadmaps (:8001), the surface the MCP server calls.

Mirrors the external ``/roadmaps`` router (:mod:`wren.roadmaps.api`) op-for-op but
resolves the caller via :func:`require_internal_user` (the trusted ``X-User-ID``
header behind the shared ``INTERNAL_API_TOKEN``, spec section 08) instead of the
human session cookie. Both are thin adapters over the same :class:`RoadmapService`:
identical business rules, different identity resolution. The internal app is never
tunnel-routed or host-published, so it is reachable only by the
MCP server on ``compute-net``; the trusted identity is taken on trust here, never
re-validated.

The MCP write/read tools are thin clients of these endpoints: one
tool call becomes one internal HTTP call carrying the resolved ``X-User-ID``. This
includes the fork and presentation-only metadata-edit tools, both agent-callable
(spec section 07).
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, Query

from wren.core.identity import require_internal_user
from wren.roadmaps.config import ROADMAPS_PATH
from wren.roadmaps.read_schemas import (
    NodeDetail,
    Overview,
    ResponseFormat,
    SearchHit,
    SectionInclude,
    SectionPage,
)
from wren.roadmaps.schemas import (
    MetadataEditRequest,
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
        # Full document to a reader: the trusted user reads their
        # own roadmap (any status) or a public published/archived one; a private
        # roadmap owned by another, or a non-owner's public draft, is a 404.
        return await service.get(user_id, roadmap_id)

    @router.get("/{roadmap_id}/overview")
    async def get_overview(
        roadmap_id: str,
        format: ResponseFormat = ResponseFormat.CONCISE,
        user_id: str = Depends(require_internal_user),
        service: RoadmapService = Depends(service_provider),
    ) -> Overview:
        # Backs the roadmap_get_overview MCP tool.
        return await service.get_overview(user_id, roadmap_id, format)

    @router.get("/{roadmap_id}/nodes/{subsection_id}")
    async def get_node(
        roadmap_id: str,
        subsection_id: str,
        format: ResponseFormat = ResponseFormat.CONCISE,
        user_id: str = Depends(require_internal_user),
        service: RoadmapService = Depends(service_provider),
    ) -> NodeDetail:
        # Backs the roadmap_get_node MCP tool: unknown id -> 404 naming
        # valid siblings so the agent can self-correct.
        return await service.get_node(user_id, roadmap_id, subsection_id, format)

    @router.get("/{roadmap_id}/sections/{section_id}")
    async def get_section(
        roadmap_id: str,
        section_id: str,
        cursor: str | None = None,
        include: SectionInclude = SectionInclude.BOTH,
        user_id: str = Depends(require_internal_user),
        service: RoadmapService = Depends(service_provider),
    ) -> SectionPage:
        # Backs the roadmap_get_section MCP tool: opaque cursor + include.
        return await service.get_section(user_id, roadmap_id, section_id, cursor, include)

    @router.get("/{roadmap_id}/search")
    async def search_roadmap(
        roadmap_id: str,
        q: str | None = None,
        tags: list[str] | None = Query(default=None),
        user_id: str = Depends(require_internal_user),
        service: RoadmapService = Depends(service_provider),
    ) -> list[SearchHit]:
        # Backs the roadmap_search MCP tool: search, not list-all.
        return await service.search(user_id, roadmap_id, q, tags)

    @router.patch("/{roadmap_id}")
    async def patch_roadmap(
        roadmap_id: str,
        body: PatchRequest,
        if_match: int = Header(alias="If-Match"),
        user_id: str = Depends(require_internal_user),
        service: RoadmapService = Depends(service_provider),
    ) -> PatchResult:
        # If-Match carries the target revision: a mismatch is a
        # 409 "re-read", an invalid op is a 422, both rendered by the shared
        # exception handler. A malformed/absent header is a 422 via FastAPI.
        return await service.patch_draft(user_id, roadmap_id, if_match, body.operations)

    @router.put("/{roadmap_id}")
    async def replace_roadmap(
        roadmap_id: str,
        body: RoadmapInput,
        if_match: int = Header(alias="If-Match"),
        user_id: str = Depends(require_internal_user),
        service: RoadmapService = Depends(service_provider),
    ) -> RoadmapReplaced:
        # The full-document import escape hatch backing the replace_roadmap_draft MCP
        # tool: guarded by the same If-Match optimistic concurrency and
        # immutability boundary as the external route.
        return await service.replace_draft(user_id, roadmap_id, if_match, body)

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

    @router.post("/{roadmap_id}:fork", status_code=201)
    async def fork_roadmap(
        roadmap_id: str,
        user_id: str = Depends(require_internal_user),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        # Backs the fork MCP tool: forks any roadmap the trusted user
        # can read into a fresh draft with a new roadmap ID and no progress
        # carry-over; an unreadable source is a 404 (no existence leak).
        return await service.fork(user_id, roadmap_id)

    @router.patch("/{roadmap_id}/metadata")
    async def edit_roadmap_metadata(
        roadmap_id: str,
        body: MetadataEditRequest,
        user_id: str = Depends(require_internal_user),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        # Backs the edit_metadata MCP tool: presentation-only, allowed
        # post-publish, not If-Match-guarded; a smuggled structural field is a 409
        # IMMUTABLE at the wire boundary.
        body.reject_structural_fields()
        return await service.edit_metadata(
            user_id, roadmap_id, body.title, body.description, body.subject_tags
        )

    return router
