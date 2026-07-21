"""REST adapter factory for progress, one factory for both trust boundaries.

The external app (:8000) and the internal app (:8001) mount the same progress
handlers: the handler bodies are identical and differ only in which routes mount
and how the caller's ``user_id`` is resolved. Rather than fork the router or pass
those two facts in by hand, :func:`create_progress_router` takes an :class:`App`
selector and reads both from the route registry:

- **mounting** (composition): a route mounts on the app iff that app's registry
  declares it. ``follow`` and ``deadline`` are declared for the external app only
  (following is created implicitly by the first progress write, and deadline is
  web-only, deliberately unmirrored in the MCP contract), so the internal app the
  MCP server calls mounts only snapshot / explicit-set / next.
- **identity** (policy): each route resolves the identity dependency its declared
  access level maps to: ``require_user`` (external cookie) or
  ``require_internal_user`` (the trusted ``X-User-ID`` behind ``INTERNAL_API_TOKEN``).

Thin handlers: each resolves the caller via the resolved ``identity`` dependency,
calls one :class:`ProgressService` method, and lets the shared exception handler
render any ``WrenError`` as RFC 9457 problem+json. The service scopes every query
to the resolved user, so a tool can never reach another user's progress even
though the internal app trusts the injected identity. These routes hang under the
``/roadmaps/{id}`` resource and are all owner-or-follower reads/writes scoped to
the resolved user.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends

from wren.core.read_contract import ResponseFormat
from wren.core.route_registry import IDENTITY_BY_ACCESS, App, Identity, RouteKey, route_access

# The schema/service imports below suppress TC001: FastAPI evaluates a handler's
# parameter/return annotations at runtime (via get_type_hints when the route is
# registered), so they must stay runtime imports. The repo's flake8-type-checking
# config whitelists the @router.* route decorators, but this factory registers via
# add_api_route in a loop, which that config does not cover; moving them into a
# type-checking block would NameError at registration.
from wren.progress.schemas import (
    DeadlineRequest,  # noqa: TC001
    NextResult,  # noqa: TC001
    Progress,  # noqa: TC001
    ProgressSnapshot,  # noqa: TC001
    ProgressUpdateRequest,  # noqa: TC001
    ProgressUpdateResult,  # noqa: TC001
)
from wren.progress.service import ProgressService  # noqa: TC001
from wren.roadmaps.config import ROADMAPS_PATH

# A FastAPI dependency that yields a ProgressService for the request.
ProgressServiceProvider = Callable[..., object]

# An endpoint builder: given the resolved identity dependency, returns the route
# handler (closing over the injected service provider).
_Endpoint = Callable[..., Awaitable[object]]
_Builder = Callable[[Identity], _Endpoint]


def create_progress_router(service_provider: ProgressServiceProvider, *, app: App) -> APIRouter:
    """Build the progress router for ``app``, driven by the route registry.

    Injects the progress service provider (request-scoped). The set of routes
    mounted and the identity each resolves both come from ``app``'s registry (see
    the module docstring): the internal app mounts only snapshot / explicit-set /
    next, while the external app additionally mounts the web-only follow / deadline
    routes. The service scopes every query to the resolved user, so the internal
    app can trust the injected identity without a route reaching another user's
    progress.
    """
    router = APIRouter(prefix=ROADMAPS_PATH, tags=["progress"])
    registry = route_access(app)

    def _follow(identity: Identity) -> _Endpoint:
        async def follow_roadmap(
            roadmap_id: str,
            user_id: str = Depends(identity),
            service: ProgressService = Depends(service_provider),
        ) -> Progress:
            return await service.follow(user_id, roadmap_id)

        return follow_roadmap

    def _get(identity: Identity) -> _Endpoint:
        async def get_progress(
            roadmap_id: str,
            detailed: bool = False,
            user_id: str = Depends(identity),
            service: ProgressService = Depends(service_provider),
        ) -> ProgressSnapshot:
            return await service.get(user_id, roadmap_id, detailed)

        return get_progress

    def _update(identity: Identity) -> _Endpoint:
        async def update_progress(
            roadmap_id: str,
            body: ProgressUpdateRequest,
            user_id: str = Depends(identity),
            service: ProgressService = Depends(service_provider),
        ) -> ProgressUpdateResult:
            return await service.update(user_id, roadmap_id, body.item_ids, body.state)

        return update_progress

    def _next(identity: Identity) -> _Endpoint:
        async def get_next(
            roadmap_id: str,
            format: ResponseFormat = ResponseFormat.CONCISE,
            user_id: str = Depends(identity),
            service: ProgressService = Depends(service_provider),
        ) -> NextResult:
            # Server-computed next items with a structural why_now + resource links;
            # detailed adds each item's path_position (never delegated to the agent).
            return await service.get_next(user_id, roadmap_id, format)

        return get_next

    def _deadline(identity: Identity) -> _Endpoint:
        async def set_deadline(
            roadmap_id: str,
            body: DeadlineRequest,
            user_id: str = Depends(identity),
            service: ProgressService = Depends(service_provider),
        ) -> Progress:
            # Set (a date) or clear (null) the per-user deadline; editable anytime,
            # a past date is allowed (countdown only, no pacing signal).
            return await service.set_deadline(user_id, roadmap_id, body.deadline)

        return set_deadline

    # The route table, in the external OpenAPI declaration order. follow and
    # deadline are declared for the external app only, so the internal app skips
    # them. Status codes carry per-route (201 follow); response models are inferred
    # from the handler return annotations.
    table: list[tuple[RouteKey, _Builder, int]] = [
        (RouteKey(method="POST", path=f"{ROADMAPS_PATH}/{{roadmap_id}}/follow"), _follow, 201),
        (RouteKey(method="GET", path=f"{ROADMAPS_PATH}/{{roadmap_id}}/progress"), _get, 200),
        (RouteKey(method="POST", path=f"{ROADMAPS_PATH}/{{roadmap_id}}/progress"), _update, 200),
        (RouteKey(method="GET", path=f"{ROADMAPS_PATH}/{{roadmap_id}}/next"), _next, 200),
        (RouteKey(method="PUT", path=f"{ROADMAPS_PATH}/{{roadmap_id}}/deadline"), _deadline, 200),
    ]

    # Membership in ``registry`` is the mounting decision (composition); the mapped
    # access level resolves the identity (policy). A declared progress route always
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
