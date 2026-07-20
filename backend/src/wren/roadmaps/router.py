"""REST adapter factory for roadmaps, one factory for both trust boundaries.

The external app (:8000) and the internal app (:8001) mount the same ``/roadmaps``
handlers: the handler bodies are identical and differ only in how the caller's
``user_id`` is resolved. Rather than fork the router into two byte-identical
modules, :func:`create_roadmaps_router` takes the identity resolution as an
injected dependency (the standards' "inject strategy, don't fork on context"):

- **External (:8000)** passes ``identity=require_user`` (the human session cookie;
  a spoofed ``X-User-ID`` is stripped upstream).
- **Internal (:8001)** passes ``identity=require_internal_user`` (the trusted
  ``X-User-ID`` behind the shared ``INTERNAL_API_TOKEN``).

The three web-only lifecycle routes (``PUT /roadmaps/{id}/visibility``,
``POST /roadmaps/{id}:archive``, ``DELETE /roadmaps/{id}``) live in a separate
factory, :func:`create_roadmaps_web_lifecycle_router`, that only the external
entrypoint mounts. Composing the surface difference at the mount site keeps each
factory free of a "which app am I" branch: the internal app (which the MCP server
calls) never builds these routes, so they have no internal-app route and no MCP
tool.

Thin handlers: each resolves the caller via the injected ``identity`` dependency,
calls one :class:`RoadmapService` / :class:`RoadmapReadService` method, and lets
the shared exception handler render any ``WrenError`` as RFC 9457 problem+json.
The services are injected via ``service_provider`` / ``read_service_provider`` so
production binds a request-scoped DB session while tests substitute an
in-memory-backed service.

The lifecycle commands use the ``:verb`` action sub-resource form
(``POST /roadmaps/{id}:validate`` / ``:publish`` / ``:fork``); ``publish``
hard-blocks with a 422 carrying the ``Violation`` list, while ``validate`` always
returns 200 with a (possibly empty) list and ``fork`` returns 201 with the new
draft. ``PATCH /roadmaps/{id}/metadata`` is the presentation-only edit that stays
allowed post-publish (not ``If-Match``-guarded). The three web-only lifecycle
actions live in :func:`create_roadmaps_web_lifecycle_router`, which the external
entrypoint mounts alongside the core router. Delete is guarded by a zero-followers
check (409 ``DELETE_HAS_FOLLOWERS`` otherwise); archive is the safe retirement
path.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Header, Query

from wren.core.read_contract import ResponseFormat
from wren.roadmaps.config import ROADMAPS_PATH
from wren.roadmaps.read_schemas import (
    NodeDetail,
    Overview,
    SearchHit,
    SectionInclude,
    SectionPage,
)
from wren.roadmaps.read_service import RoadmapReadService
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

# A FastAPI dependency that resolves the request's ``user_id`` at the trust
# boundary: ``require_user`` (external cookie) or ``require_internal_user``
# (internal trusted header). Injected so one factory serves both apps.
Identity = Callable[..., Awaitable[str]]
# A FastAPI dependency that yields a RoadmapService for the request.
RoadmapServiceProvider = Callable[..., object]
# A FastAPI dependency that yields a RoadmapReadService for the request.
RoadmapReadServiceProvider = Callable[..., object]


def create_roadmaps_router(
    service_provider: RoadmapServiceProvider,
    read_service_provider: RoadmapReadServiceProvider,
    *,
    identity: Identity,
) -> APIRouter:
    """Build the core /roadmaps router, parameterized by the injected identity.

    Injects the authoring/lifecycle service provider (writes + lifecycle), the read
    service provider (the study-time reads, each request-scoped), and the
    ``identity`` dependency every handler resolves ``user_id`` from. The service
    scopes every query to that user, so the internal app can trust the injected
    identity without a route ever reaching another user's roadmap. The three
    web-only lifecycle routes (visibility / archive / delete) are built by
    :func:`create_roadmaps_web_lifecycle_router` and mounted by the external
    entrypoint only, so this router is identical on both apps.
    """
    router = APIRouter(prefix=ROADMAPS_PATH, tags=["roadmaps"])

    @router.post("", status_code=201)
    async def create_roadmap(
        body: RoadmapInput,
        user_id: str = Depends(identity),
        service: RoadmapService = Depends(service_provider),
    ) -> RoadmapCreated:
        return await service.create_draft(user_id, body)

    @router.get("/{roadmap_id}")
    async def get_roadmap(
        roadmap_id: str,
        user_id: str = Depends(identity),
        service: RoadmapReadService = Depends(read_service_provider),
    ) -> Roadmap:
        # Full document to a reader: the owner (any status, draft
        # preview) or a non-owner reading a public published/archived roadmap by
        # link. A private roadmap or a non-owner's public draft is a 404 (no leak).
        return await service.get(user_id, roadmap_id)

    @router.get("/{roadmap_id}/overview")
    async def get_overview(
        roadmap_id: str,
        format: ResponseFormat = ResponseFormat.CONCISE,
        user_id: str = Depends(identity),
        service: RoadmapReadService = Depends(read_service_provider),
    ) -> Overview:
        # Orientation projection: per-section + overall counts, no item bodies.
        return await service.get_overview(user_id, roadmap_id, format)

    @router.get("/{roadmap_id}/nodes/{subsection_id}")
    async def get_node(
        roadmap_id: str,
        subsection_id: str,
        format: ResponseFormat = ResponseFormat.CONCISE,
        user_id: str = Depends(identity),
        service: RoadmapReadService = Depends(read_service_provider),
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
        user_id: str = Depends(identity),
        service: RoadmapReadService = Depends(read_service_provider),
    ) -> SectionPage:
        # Paginated drill-down: server-set page size + opaque cursor; a stale or
        # malformed cursor is a 422 via the shared exception handler.
        return await service.get_section(user_id, roadmap_id, section_id, cursor, include)

    @router.get("/{roadmap_id}/search")
    async def search_roadmap(
        roadmap_id: str,
        q: str | None = None,
        tags: list[str] | None = Query(default=None),
        user_id: str = Depends(identity),
        service: RoadmapReadService = Depends(read_service_provider),
    ) -> list[SearchHit]:
        # Search, not list-all: an empty query with no tag filter returns [].
        return await service.search(user_id, roadmap_id, q, tags)

    @router.patch("/{roadmap_id}")
    async def patch_roadmap(
        roadmap_id: str,
        body: PatchRequest,
        if_match: int = Header(alias="If-Match"),
        user_id: str = Depends(identity),
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
        user_id: str = Depends(identity),
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
        user_id: str = Depends(identity),
        service: RoadmapService = Depends(service_provider),
    ) -> ValidateResult:
        violations = await service.validate(user_id, roadmap_id)
        return ValidateResult(violations=violations)

    @router.post("/{roadmap_id}:publish")
    async def publish_roadmap(
        roadmap_id: str,
        user_id: str = Depends(identity),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        return await service.publish(user_id, roadmap_id)

    @router.post("/{roadmap_id}:fork", status_code=201)
    async def fork_roadmap(
        roadmap_id: str,
        user_id: str = Depends(identity),
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
        user_id: str = Depends(identity),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        # Presentation-only edit, allowed even when published: not
        # If-Match-guarded and never bumps the structural revision. A smuggled
        # structural/lifecycle field is rejected 409 IMMUTABLE at the wire boundary.
        body.reject_structural_fields()
        return await service.edit_metadata(
            user_id, roadmap_id, body.title, body.description, body.subject_tags
        )

    return router


def create_roadmaps_web_lifecycle_router(
    service_provider: RoadmapServiceProvider, *, identity: Identity
) -> APIRouter:
    """Build the three web-only lifecycle routes (visibility / archive / delete).

    Mounted by the external entrypoint only, alongside
    :func:`create_roadmaps_router`, so the internal app (the MCP surface) never
    exposes them: there is no internal-app route and no MCP tool for visibility /
    archive / delete. All three resolve the caller via the same injected
    ``identity`` dependency and are owner-scoped in the service (a non-owner is a
    404, no existence leak).
    """
    router = APIRouter(prefix=ROADMAPS_PATH, tags=["roadmaps"])

    @router.put("/{roadmap_id}/visibility")
    async def set_roadmap_visibility(
        roadmap_id: str,
        body: VisibilityRequest,
        user_id: str = Depends(identity),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        # Web-only visibility toggle: mounted on the external
        # app only, no internal-app route and no MCP tool. Owner-scoped in the
        # service (a non-owner is a 404, no existence leak); last-write-wins.
        return await service.set_visibility(user_id, roadmap_id, body.visibility)

    @router.post("/{roadmap_id}:archive")
    async def archive_roadmap(
        roadmap_id: str,
        user_id: str = Depends(identity),
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
        user_id: str = Depends(identity),
        service: RoadmapService = Depends(service_provider),
    ) -> None:
        # Web-only delete: external app only, no internal-app
        # route and no MCP tool. Guarded by a zero-followers check in the service; a
        # roadmap with followers is a 409 DELETE_HAS_FOLLOWERS steering to archive.
        await service.delete(user_id, roadmap_id)

    return router
