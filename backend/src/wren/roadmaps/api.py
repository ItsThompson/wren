"""External REST adapter for roadmaps: create, read, iterative-edit (patch),
full-document import (replace), validate, publish, fork, presentation-only
metadata edit, and the web-only lifecycle (visibility / archive / delete).

Thin handlers: each resolves the caller via ``require_user``
(the cookie session; a spoofed ``X-User-ID`` is stripped upstream), calls one
:class:`RoadmapService` method, and lets the shared exception handler render any
``WrenError`` as RFC 9457 problem+json. The service is injected via
``service_provider`` so production binds a request-scoped DB session while tests
substitute an in-memory-backed service.

The lifecycle commands use the ``:verb`` action sub-resource form
(``POST /roadmaps/{id}:validate`` / ``:publish`` / ``:fork``); ``publish``
hard-blocks with a 422 carrying the ``Violation`` list, while ``validate`` always
returns 200 with a (possibly empty) list and ``fork`` returns 201 with the new
draft. ``PATCH /roadmaps/{id}/metadata`` is the presentation-only edit that stays
allowed post-publish (not ``If-Match``-guarded). The web-only lifecycle actions
(``PUT /roadmaps/{id}/visibility``, ``POST /roadmaps/{id}:archive``,
``DELETE /roadmaps/{id}``) are mounted on the external app **only**: they have no
internal-app route and no MCP tool. Delete is guarded by
a zero-followers check (409 ``DELETE_HAS_FOLLOWERS`` otherwise); archive is the
safe retirement path.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, Query

from wren.core.identity import require_user
from wren.core.read_contract import ResponseFormat
from wren.roadmaps.config import ROADMAPS_PATH
from wren.roadmaps.read_schemas import (
    NodeDetail,
    Overview,
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
    VisibilityRequest,
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
        # Full document to a reader: the owner (any status, draft
        # preview) or a non-owner reading a public published/archived roadmap by
        # link. A private roadmap or a non-owner's public draft is a 404 (no leak).
        return await service.get(user_id, roadmap_id)

    @router.get("/{roadmap_id}/overview")
    async def get_overview(
        roadmap_id: str,
        format: ResponseFormat = ResponseFormat.CONCISE,
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> Overview:
        # Orientation projection: per-section + overall counts, no item bodies.
        return await service.get_overview(user_id, roadmap_id, format)

    @router.get("/{roadmap_id}/nodes/{subsection_id}")
    async def get_node(
        roadmap_id: str,
        subsection_id: str,
        format: ResponseFormat = ResponseFormat.CONCISE,
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> NodeDetail:
        # One subsection: resource links (never inlined bodies), resolved prereqs,
        # and items with the caller's done-state. Unknown id -> 404 naming siblings.
        return await service.get_node(user_id, roadmap_id, subsection_id, format)

    @router.get("/{roadmap_id}/sections/{section_id}")
    async def get_section(
        roadmap_id: str,
        section_id: str,
        cursor: str | None = None,
        include: SectionInclude = SectionInclude.BOTH,
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> SectionPage:
        # Paginated drill-down: server-set page size + opaque cursor; a stale or
        # malformed cursor is a 422 via the shared exception handler.
        return await service.get_section(user_id, roadmap_id, section_id, cursor, include)

    @router.get("/{roadmap_id}/search")
    async def search_roadmap(
        roadmap_id: str,
        q: str | None = None,
        tags: list[str] | None = Query(default=None),
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> list[SearchHit]:
        # Search, not list-all: an empty query with no tag filter returns [].
        return await service.search(user_id, roadmap_id, q, tags)

    @router.patch("/{roadmap_id}")
    async def patch_roadmap(
        roadmap_id: str,
        body: PatchRequest,
        if_match: int = Header(alias="If-Match"),
        user_id: str = Depends(require_user),
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
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> RoadmapReplaced:
        # The full-document import escape hatch, never the
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

    @router.post("/{roadmap_id}:fork", status_code=201)
    async def fork_roadmap(
        roadmap_id: str,
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        # Fork any roadmap the caller can read (own, or public): a new draft with a
        # freshly-minted roadmap ID and no progress carry-over.
        # An unreadable source is a 404 (no existence leak) via the service.
        return await service.fork(user_id, roadmap_id)

    @router.patch("/{roadmap_id}/metadata")
    async def edit_roadmap_metadata(
        roadmap_id: str,
        body: MetadataEditRequest,
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        # Presentation-only edit, allowed even when published: not
        # If-Match-guarded and never bumps the structural revision. A smuggled
        # structural/lifecycle field is rejected 409 IMMUTABLE at the wire boundary.
        body.reject_structural_fields()
        return await service.edit_metadata(
            user_id, roadmap_id, body.title, body.description, body.subject_tags
        )

    @router.put("/{roadmap_id}/visibility")
    async def set_roadmap_visibility(
        roadmap_id: str,
        body: VisibilityRequest,
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        # Web-only visibility toggle: mounted on the external
        # app only, no internal-app route and no MCP tool. Owner-scoped in the
        # service (a non-owner is a 404, no existence leak); last-write-wins.
        return await service.set_visibility(user_id, roadmap_id, body.visibility)

    @router.post("/{roadmap_id}:archive")
    async def archive_roadmap(
        roadmap_id: str,
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        # Web-only archive: the safe retirement path (hides
        # from discovery, existing followers keep access). External app only, no
        # internal-app route and no MCP tool. Only a published roadmap can be
        # archived (else 409 via the service).
        return await service.archive(user_id, roadmap_id)

    @router.delete("/{roadmap_id}", status_code=204)
    async def delete_roadmap(
        roadmap_id: str,
        user_id: str = Depends(require_user),
        service: RoadmapService = Depends(service_provider),
    ) -> None:
        # Web-only delete: external app only, no internal-app
        # route and no MCP tool. Guarded by a zero-followers check in the service; a
        # roadmap with followers is a 409 DELETE_HAS_FOLLOWERS steering to archive.
        await service.delete(user_id, roadmap_id)

    return router
