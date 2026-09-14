"""REST adapter factory for roadmaps across both trust boundaries.

The external and internal apps mount the same handlers. The route registry selects
both the identity dependency and the routes each app exposes. ``require_user``
resolves external cookie identity, while ``require_internal_user`` trusts the
internal token boundary. ``restrict_to_declared`` removes external-only lifecycle
routes from the internal app.

Handlers resolve identity, call one injected service method, and rely on shared
exception handling for ``WrenError`` responses. Providers keep service creation
request-scoped in production and replaceable in tests. Lifecycle commands use
``:verb`` action routes; metadata remains editable after publish, while archive
provides the safe retirement path.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, Query
from starlette.responses import Response

from wren.core.identity import require_user
from wren.core.read_contract import ResponseFormat
from wren.core.route_registry import (
    AccessLevel,
    App,
    RequiredIdentity,
    RouteKey,
    optional_identity_for_route,
    required_identity_for_route,
    restrict_to_declared,
    route_access,
)
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
    PublishedVisibilityRequest,
    Roadmap,
    RoadmapCreated,
    RoadmapInput,
    RoadmapReplaced,
    ValidateResult,
)
from wren.roadmaps.service import RoadmapService

# A FastAPI dependency that yields a RoadmapService for the request.
RoadmapServiceProvider = Callable[..., object]
# A FastAPI dependency that yields a RoadmapReadService for the request.
RoadmapReadServiceProvider = Callable[..., object]


def create_roadmaps_router(
    service_provider: RoadmapServiceProvider,
    read_service_provider: RoadmapReadServiceProvider,
    *,
    app: App,
) -> APIRouter:
    """Build the /roadmaps router for ``app`` from the route registry."""
    router = APIRouter(prefix=ROADMAPS_PATH, tags=["roadmaps"])
    registry = route_access(app)

    def required_identity(method: str, path: str) -> RequiredIdentity:
        key = RouteKey(method=method, path=path)
        if key not in registry:
            return require_user
        return required_identity_for_route(app, key)

    document_key = RouteKey(method="GET", path="/roadmaps/{roadmap_id}")
    document_level = registry[document_key]
    document_identity = (
        optional_identity_for_route(app, document_key)
        if document_level is AccessLevel.OPTIONAL_SESSION
        else required_identity_for_route(app, document_key)
    )

    create_identity = required_identity("POST", "/roadmaps")
    patch_identity = required_identity("PATCH", "/roadmaps/{roadmap_id}")
    replace_identity = required_identity("PUT", "/roadmaps/{roadmap_id}")
    validate_identity = required_identity("POST", "/roadmaps/{roadmap_id}:validate")
    publish_identity = required_identity("POST", "/roadmaps/{roadmap_id}:publish")
    fork_identity = required_identity("POST", "/roadmaps/{roadmap_id}:fork")
    metadata_identity = required_identity("PATCH", "/roadmaps/{roadmap_id}/metadata")
    published_visibility_identity = required_identity(
        "PUT", "/roadmaps/{roadmap_id}/published-visibility"
    )
    archive_identity = required_identity("POST", "/roadmaps/{roadmap_id}:archive")
    delete_identity = required_identity("DELETE", "/roadmaps/{roadmap_id}")
    overview_identity = required_identity("GET", "/roadmaps/{roadmap_id}/overview")
    node_identity = required_identity("GET", "/roadmaps/{roadmap_id}/nodes/{subsection_id}")
    section_identity = required_identity("GET", "/roadmaps/{roadmap_id}/sections/{section_id}")
    search_identity = required_identity("GET", "/roadmaps/{roadmap_id}/search")

    @router.post("", status_code=201)
    async def create_roadmap(
        body: RoadmapInput,
        user_id: str = Depends(create_identity),
        service: RoadmapService = Depends(service_provider),
    ) -> RoadmapCreated:
        return await service.create_draft(user_id, body)

    @router.get("/{roadmap_id}")
    async def get_roadmap(
        roadmap_id: str,
        response: Response,
        user_id: str | None = Depends(document_identity),
        service: RoadmapReadService = Depends(read_service_provider),
    ) -> Roadmap:
        # Full document to a reader: the owner (any status, draft
        # preview) or a non-owner reading a public published/archived roadmap by
        # link. A private roadmap or a non-owner's public draft is a 404 (no leak).
        response.headers["Cache-Control"] = "no-store"
        return await service.get(user_id, roadmap_id)

    @router.get("/{roadmap_id}/overview")
    async def get_overview(
        roadmap_id: str,
        format: ResponseFormat = ResponseFormat.CONCISE,
        user_id: str = Depends(overview_identity),
        service: RoadmapReadService = Depends(read_service_provider),
    ) -> Overview:
        # Orientation projection: per-section + overall counts, no item bodies.
        return await service.get_overview(user_id, roadmap_id, format)

    @router.get("/{roadmap_id}/nodes/{subsection_id}")
    async def get_node(
        roadmap_id: str,
        subsection_id: str,
        format: ResponseFormat = ResponseFormat.CONCISE,
        user_id: str = Depends(node_identity),
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
        user_id: str = Depends(section_identity),
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
        user_id: str = Depends(search_identity),
        service: RoadmapReadService = Depends(read_service_provider),
    ) -> list[SearchHit]:
        # Search, not list-all: an empty query with no tag filter returns [].
        return await service.search(user_id, roadmap_id, q, tags)

    @router.patch("/{roadmap_id}")
    async def patch_roadmap(
        roadmap_id: str,
        body: PatchRequest,
        if_match: int = Header(alias="If-Match"),
        user_id: str = Depends(patch_identity),
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
        user_id: str = Depends(replace_identity),
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
        user_id: str = Depends(validate_identity),
        service: RoadmapService = Depends(service_provider),
    ) -> ValidateResult:
        violations = await service.validate(user_id, roadmap_id)
        return ValidateResult(violations=violations)

    @router.post("/{roadmap_id}:publish")
    async def publish_roadmap(
        roadmap_id: str,
        user_id: str = Depends(publish_identity),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        return await service.publish(user_id, roadmap_id)

    @router.post("/{roadmap_id}:fork", status_code=201)
    async def fork_roadmap(
        roadmap_id: str,
        user_id: str = Depends(fork_identity),
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
        user_id: str = Depends(metadata_identity),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        # Presentation-only edit, allowed even when published: not
        # If-Match-guarded and never bumps the structural revision. A smuggled
        # structural/lifecycle field is rejected 409 IMMUTABLE at the wire boundary.
        body.reject_structural_fields()
        return await service.edit_metadata(
            user_id, roadmap_id, body.title, body.description, body.subject_tags
        )

    @router.put("/{roadmap_id}/published-visibility")
    async def set_roadmap_published_visibility(
        roadmap_id: str,
        body: PublishedVisibilityRequest,
        user_id: str = Depends(published_visibility_identity),
        service: RoadmapService = Depends(service_provider),
    ) -> Roadmap:
        # Web-only publication-access toggle: external app only, no internal-app
        # route and no MCP tool. Owner-scoped in the service.
        return await service.set_published_visibility(
            user_id, roadmap_id, body.published_visibility
        )

    @router.post("/{roadmap_id}:archive")
    async def archive_roadmap(
        roadmap_id: str,
        user_id: str = Depends(archive_identity),
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
        user_id: str = Depends(delete_identity),
        service: RoadmapService = Depends(service_provider),
    ) -> None:
        # Web-only delete: external app only, no internal-app
        # route and no MCP tool. Guarded by a zero-followers check in the service; a
        # roadmap with followers is a 409 DELETE_HAS_FOLLOWERS steering to archive.
        await service.delete(user_id, roadmap_id)

    # Composition from the registry: keep only the routes this app declares (the
    # web-only lifecycle routes are external-only).
    restrict_to_declared(router, app)
    return router
