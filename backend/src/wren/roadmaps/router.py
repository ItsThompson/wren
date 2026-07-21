"""REST adapter factory for roadmaps, one factory for both trust boundaries.

The external app (:8000) and the internal app (:8001) mount the same ``/roadmaps``
handlers: the handler bodies are identical and differ only in which routes mount
and how the caller's ``user_id`` is resolved. Rather than fork the router or pass
those two facts in by hand, :func:`create_roadmaps_router` takes an :class:`App`
selector and reads both from the route registry:

- **mounting** (composition): a route mounts on the app iff that app's registry
  (:func:`wren.core.route_registry.route_access`) declares it. The web-only
  lifecycle routes (visibility / archive / delete) are declared for the external
  app only, so the internal app (the MCP surface) never mounts them.
- **identity** (policy): each route resolves the identity dependency its declared
  access level maps to (:data:`wren.core.route_registry.IDENTITY_BY_ACCESS`):
  ``require_user`` (external cookie; a spoofed ``X-User-ID`` is stripped upstream)
  or ``require_internal_user`` (the trusted ``X-User-ID`` behind the shared
  ``INTERNAL_API_TOKEN``).

Thin handlers: each resolves the caller via the resolved ``identity`` dependency,
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
actions are external-app only: delete is guarded by a zero-followers check (409
``DELETE_HAS_FOLLOWERS`` otherwise) and archive is the safe retirement path.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Header, Query

from wren.core.read_contract import ResponseFormat
from wren.core.route_registry import IDENTITY_BY_ACCESS, App, Identity, RouteKey, route_access
from wren.roadmaps.config import ROADMAPS_PATH
from wren.roadmaps.read_schemas import (
    NodeDetail,
    Overview,
    SearchHit,
    SectionInclude,
    SectionPage,
)

# The service imports below suppress TC001: FastAPI evaluates a handler's
# parameter/return annotations at runtime (via get_type_hints when the route is
# registered), so the service types used only in ``Depends(...)`` annotations must
# stay runtime imports. The repo's flake8-type-checking config whitelists the
# @router.* route decorators, but this factory registers via add_api_route in a
# loop, which that config does not cover; moving them into a type-checking block
# would NameError at registration.
from wren.roadmaps.read_service import RoadmapReadService  # noqa: TC001
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
from wren.roadmaps.service import RoadmapService  # noqa: TC001

# A FastAPI dependency that yields a RoadmapService for the request.
RoadmapServiceProvider = Callable[..., object]
# A FastAPI dependency that yields a RoadmapReadService for the request.
RoadmapReadServiceProvider = Callable[..., object]

# An endpoint builder: given the resolved identity dependency, returns the route
# handler (closing over the injected service providers).
_Endpoint = Callable[..., Awaitable[object]]
_Builder = Callable[[Identity], _Endpoint]


def create_roadmaps_router(
    service_provider: RoadmapServiceProvider,
    read_service_provider: RoadmapReadServiceProvider,
    *,
    app: App,
) -> APIRouter:
    """Build the /roadmaps router for ``app``, driven by the route registry.

    Injects the authoring/lifecycle service provider (writes + lifecycle) and the
    read service provider (the study-time reads, each request-scoped). The set of
    routes mounted and the identity each resolves both come from ``app``'s registry
    (see the module docstring), so the surface difference between the two apps
    lives in one table rather than in a flag or a forked module. The service scopes
    every query to the resolved user, so the internal app can trust the injected
    identity without a route ever reaching another user's roadmap.
    """
    router = APIRouter(prefix=ROADMAPS_PATH, tags=["roadmaps"])
    registry = route_access(app)

    def _create(identity: Identity) -> _Endpoint:
        async def create_roadmap(
            body: RoadmapInput,
            user_id: str = Depends(identity),
            service: RoadmapService = Depends(service_provider),
        ) -> RoadmapCreated:
            return await service.create_draft(user_id, body)

        return create_roadmap

    def _get(identity: Identity) -> _Endpoint:
        async def get_roadmap(
            roadmap_id: str,
            user_id: str = Depends(identity),
            service: RoadmapReadService = Depends(read_service_provider),
        ) -> Roadmap:
            # Full document to a reader: the owner (any status, draft
            # preview) or a non-owner reading a public published/archived roadmap by
            # link. A private roadmap or a non-owner's public draft is a 404 (no leak).
            return await service.get(user_id, roadmap_id)

        return get_roadmap

    def _overview(identity: Identity) -> _Endpoint:
        async def get_overview(
            roadmap_id: str,
            format: ResponseFormat = ResponseFormat.CONCISE,
            user_id: str = Depends(identity),
            service: RoadmapReadService = Depends(read_service_provider),
        ) -> Overview:
            # Orientation projection: per-section + overall counts, no item bodies.
            return await service.get_overview(user_id, roadmap_id, format)

        return get_overview

    def _node(identity: Identity) -> _Endpoint:
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

        return get_node

    def _section(identity: Identity) -> _Endpoint:
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

        return get_section

    def _search(identity: Identity) -> _Endpoint:
        async def search_roadmap(
            roadmap_id: str,
            q: str | None = None,
            tags: list[str] | None = Query(default=None),
            user_id: str = Depends(identity),
            service: RoadmapReadService = Depends(read_service_provider),
        ) -> list[SearchHit]:
            # Search, not list-all: an empty query with no tag filter returns [].
            return await service.search(user_id, roadmap_id, q, tags)

        return search_roadmap

    def _patch(identity: Identity) -> _Endpoint:
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

        return patch_roadmap

    def _replace(identity: Identity) -> _Endpoint:
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

        return replace_roadmap

    def _validate(identity: Identity) -> _Endpoint:
        async def validate_roadmap(
            roadmap_id: str,
            user_id: str = Depends(identity),
            service: RoadmapService = Depends(service_provider),
        ) -> ValidateResult:
            violations = await service.validate(user_id, roadmap_id)
            return ValidateResult(violations=violations)

        return validate_roadmap

    def _publish(identity: Identity) -> _Endpoint:
        async def publish_roadmap(
            roadmap_id: str,
            user_id: str = Depends(identity),
            service: RoadmapService = Depends(service_provider),
        ) -> Roadmap:
            return await service.publish(user_id, roadmap_id)

        return publish_roadmap

    def _fork(identity: Identity) -> _Endpoint:
        async def fork_roadmap(
            roadmap_id: str,
            user_id: str = Depends(identity),
            service: RoadmapService = Depends(service_provider),
        ) -> Roadmap:
            # Fork any roadmap the caller can read (own, or public): a new draft with a
            # freshly-minted roadmap ID and no progress carry-over.
            # An unreadable source is a 404 (no existence leak) via the service.
            return await service.fork(user_id, roadmap_id)

        return fork_roadmap

    def _metadata(identity: Identity) -> _Endpoint:
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

        return edit_roadmap_metadata

    def _visibility(identity: Identity) -> _Endpoint:
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

        return set_roadmap_visibility

    def _archive(identity: Identity) -> _Endpoint:
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

        return archive_roadmap

    def _delete(identity: Identity) -> _Endpoint:
        async def delete_roadmap(
            roadmap_id: str,
            user_id: str = Depends(identity),
            service: RoadmapService = Depends(service_provider),
        ) -> None:
            # Web-only delete: external app only, no internal-app
            # route and no MCP tool. Guarded by a zero-followers check in the service; a
            # roadmap with followers is a 409 DELETE_HAS_FOLLOWERS steering to archive.
            await service.delete(user_id, roadmap_id)

        return delete_roadmap

    # The route table, in the external OpenAPI declaration order. Each entry mounts
    # only when ``app``'s registry declares the route, resolving that route's
    # identity from its access level. Status codes carry per-route (201 create/fork,
    # 204 delete); response models are inferred from the handler return annotations.
    table: list[tuple[RouteKey, _Builder, int]] = [
        (RouteKey(method="POST", path=ROADMAPS_PATH), _create, 201),
        (RouteKey(method="GET", path=f"{ROADMAPS_PATH}/{{roadmap_id}}"), _get, 200),
        (RouteKey(method="GET", path=f"{ROADMAPS_PATH}/{{roadmap_id}}/overview"), _overview, 200),
        (
            RouteKey(method="GET", path=f"{ROADMAPS_PATH}/{{roadmap_id}}/nodes/{{subsection_id}}"),
            _node,
            200,
        ),
        (
            RouteKey(method="GET", path=f"{ROADMAPS_PATH}/{{roadmap_id}}/sections/{{section_id}}"),
            _section,
            200,
        ),
        (RouteKey(method="GET", path=f"{ROADMAPS_PATH}/{{roadmap_id}}/search"), _search, 200),
        (RouteKey(method="PATCH", path=f"{ROADMAPS_PATH}/{{roadmap_id}}"), _patch, 200),
        (RouteKey(method="PUT", path=f"{ROADMAPS_PATH}/{{roadmap_id}}"), _replace, 200),
        (RouteKey(method="POST", path=f"{ROADMAPS_PATH}/{{roadmap_id}}:validate"), _validate, 200),
        (RouteKey(method="POST", path=f"{ROADMAPS_PATH}/{{roadmap_id}}:publish"), _publish, 200),
        (RouteKey(method="POST", path=f"{ROADMAPS_PATH}/{{roadmap_id}}:fork"), _fork, 201),
        (RouteKey(method="PATCH", path=f"{ROADMAPS_PATH}/{{roadmap_id}}/metadata"), _metadata, 200),
        (
            RouteKey(method="PUT", path=f"{ROADMAPS_PATH}/{{roadmap_id}}/visibility"),
            _visibility,
            200,
        ),
        (RouteKey(method="POST", path=f"{ROADMAPS_PATH}/{{roadmap_id}}:archive"), _archive, 200),
        (RouteKey(method="DELETE", path=f"{ROADMAPS_PATH}/{{roadmap_id}}"), _delete, 204),
    ]

    # Membership in ``registry`` is the mounting decision (composition); the mapped
    # access level resolves the identity (policy). A declared roadmaps route always
    # gates identity, so a None resolution is a wiring bug that fails loudly rather
    # than mounting an unguarded route.
    for key, build, status_code in table:
        if key not in registry:
            continue
        identity = IDENTITY_BY_ACCESS[registry[key]]
        if identity is None:
            raise RuntimeError(f"{key} resolves no identity dependency; refusing to mount.")
        router.add_api_route(
            key.path.removeprefix(ROADMAPS_PATH),
            build(identity),
            methods=[key.method],
            status_code=status_code,
        )
    return router
