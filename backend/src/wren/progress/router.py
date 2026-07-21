"""REST adapter factory for progress, one factory for both trust boundaries.

The external app (:8000) and the internal app (:8001) both mount the core progress
handlers (snapshot / explicit-set / next); the handler bodies are identical and
differ only in how the caller's ``user_id`` is resolved. Rather than fork the
router into two byte-identical modules, :func:`create_progress_router` takes the
identity resolution as an injected dependency (the standards' "inject strategy,
don't fork on context"):

- **External (:8000)** passes ``identity=require_user`` (the human session cookie;
  a spoofed ``X-User-ID`` is stripped upstream).
- **Internal (:8001)** passes ``identity=require_internal_user`` (the trusted
  ``X-User-ID`` behind the shared ``INTERNAL_API_TOKEN``). The MCP progress tools
  call exactly these three endpoints (``progress_get``, ``roadmap_get_next``,
  ``progress_update``), one internal HTTP call per tool.

``follow`` and ``deadline`` are web-only: no MCP tool calls them (following is
created implicitly by the first progress write, and deadline is deliberately
unmirrored in the MCP contract). They live in
:func:`create_progress_web_only_router`, which only the external entrypoint
mounts, so the internal app (the MCP surface) never exposes them and they have no
internal-app route.

Thin handlers: each resolves the caller via the injected ``identity`` dependency,
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

# A FastAPI dependency that resolves the request's ``user_id`` at the trust
# boundary: ``require_user`` (external cookie) or ``require_internal_user``
# (internal trusted header). Injected so one factory serves both apps.
Identity = Callable[..., Awaitable[str]]
# A FastAPI dependency that yields a ProgressService for the request.
ProgressServiceProvider = Callable[..., object]


def create_progress_router(
    service_provider: ProgressServiceProvider, *, identity: Identity
) -> APIRouter:
    """Build the core progress router (snapshot / explicit-set / next).

    Injects the progress service provider (request-scoped) and the ``identity``
    dependency every handler resolves ``user_id`` from. The service scopes every
    query to that user, so the internal app can trust the injected identity without
    a route ever reaching another user's progress. These three routes are the ones
    the MCP progress tools consume; ``follow`` and ``deadline`` are built by
    :func:`create_progress_web_only_router` and mounted by the external entrypoint
    only.
    """
    router = APIRouter(prefix=ROADMAPS_PATH, tags=["progress"])

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

    return router


def create_progress_web_only_router(
    service_provider: ProgressServiceProvider, *, identity: Identity
) -> APIRouter:
    """Build the two web-only progress routes (follow / deadline).

    Mounted by the external entrypoint only, alongside
    :func:`create_progress_router`, so the internal app (the MCP surface) never
    exposes them: no MCP tool follows a roadmap explicitly (the first progress
    write does it implicitly) or sets a deadline (web-only, unmirrored in the MCP
    contract). Both resolve the caller via the same injected ``identity``
    dependency and are scoped to the resolved user in the service.
    """
    router = APIRouter(prefix=ROADMAPS_PATH, tags=["progress"])

    @router.post("/{roadmap_id}/follow", status_code=201)
    async def follow_roadmap(
        roadmap_id: str,
        user_id: str = Depends(identity),
        service: ProgressService = Depends(service_provider),
    ) -> Progress:
        return await service.follow(user_id, roadmap_id)

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

    return router
