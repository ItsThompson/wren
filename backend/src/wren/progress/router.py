"""REST adapter factory for progress, one factory for both trust boundaries.

The external app (:8000) and the internal app (:8001) mount the same progress
handlers: the handler bodies are identical and differ only in which routes mount
and how the caller's ``user_id`` is resolved. Rather than fork the router or pass
those two facts in by hand, :func:`create_progress_router` takes an :class:`App`
selector and reads both from the route registry:

- **identity** (policy): :func:`identity_for_app` resolves the identity dependency
  the app's routes gate on, from their declared access level: ``require_user``
  (external cookie) or ``require_internal_user`` (the trusted ``X-User-ID`` behind
  ``INTERNAL_API_TOKEN``).
- **mounting** (composition): the factory defines every progress route, then
  :func:`restrict_to_declared` keeps only those the app's registry declares.
  ``follow`` and ``deadline`` are declared for the external app only (following is
  created implicitly by the first progress write, and deadline is web-only,
  deliberately unmirrored in the MCP contract), so the internal app the MCP server
  calls mounts only snapshot / explicit-set / next.

Thin handlers: each resolves the caller via the resolved ``identity`` dependency,
calls one :class:`ProgressService` method, and lets the shared exception handler
render any ``WrenError`` as RFC 9457 problem+json. The service scopes every query
to the resolved user, so a tool can never reach another user's progress even
though the internal app trusts the injected identity. These routes hang under the
``/roadmaps/{id}`` resource and are all owner-or-follower reads/writes scoped to
the resolved user.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends

from wren.core.read_contract import ResponseFormat
from wren.core.route_registry import App, identity_for_app, restrict_to_declared
from wren.progress.schemas import (
    DeadlineRequest,
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


def create_progress_router(service_provider: ProgressServiceProvider, *, app: App) -> APIRouter:
    """Build the progress router for ``app``, driven by the route registry.

    Injects the progress service provider (request-scoped). The identity every
    handler resolves and the subset of routes mounted both come from ``app``'s
    registry (see the module docstring): the internal app mounts only snapshot /
    explicit-set / next, while the external app additionally mounts the web-only
    follow / deadline routes. The service scopes every query to the resolved user,
    so the internal app can trust the injected identity without a route reaching
    another user's progress.
    """
    router = APIRouter(prefix=ROADMAPS_PATH, tags=["progress"])
    identity = identity_for_app(app)

    @router.post("/{roadmap_id}/follow", status_code=201)
    async def follow_roadmap(
        roadmap_id: str,
        user_id: str = Depends(identity),
        service: ProgressService = Depends(service_provider),
    ) -> Progress:
        return await service.follow(user_id, roadmap_id)

    @router.get("/{roadmap_id}/progress")
    async def get_progress(
        roadmap_id: str,
        detailed: bool = False,
        user_id: str = Depends(identity),
        service: ProgressService = Depends(service_provider),
    ) -> ProgressSnapshot:
        return await service.get(user_id, roadmap_id, detailed)

    @router.post("/{roadmap_id}/progress")
    async def update_progress(
        roadmap_id: str,
        body: ProgressUpdateRequest,
        user_id: str = Depends(identity),
        service: ProgressService = Depends(service_provider),
    ) -> ProgressUpdateResult:
        return await service.update(user_id, roadmap_id, body.item_ids, body.state)

    @router.get("/{roadmap_id}/next")
    async def get_next(
        roadmap_id: str,
        format: ResponseFormat = ResponseFormat.CONCISE,
        user_id: str = Depends(identity),
        service: ProgressService = Depends(service_provider),
    ) -> NextResult:
        # Server-computed next items with a structural why_now + resource links;
        # detailed adds each item's path_position (never delegated to the agent).
        return await service.get_next(user_id, roadmap_id, format)

    @router.put("/{roadmap_id}/deadline")
    async def set_deadline(
        roadmap_id: str,
        body: DeadlineRequest,
        user_id: str = Depends(identity),
        service: ProgressService = Depends(service_provider),
    ) -> Progress:
        # Set (a date) or clear (null) the per-user deadline; editable anytime,
        # a past date is allowed (countdown only, no pacing signal).
        return await service.set_deadline(user_id, roadmap_id, body.deadline)

    # Composition from the registry: keep only the routes this app declares (follow
    # and deadline are external-only).
    restrict_to_declared(router, app)
    return router
