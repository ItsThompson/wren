"""External REST adapter for the dashboard and public profile (spec section 06).

Thin handlers (spec sections 05/06) over :class:`ListingService`:

- ``GET /me/dashboard`` resolves the caller via ``require_user`` (the cookie
  session; a spoofed ``X-User-ID`` is stripped upstream) and returns their private
  dashboard (authored + followed).
- ``GET /users/{handle}`` is **public** (no session): it returns the handle
  owner's published-public roadmaps, or a 404 rendered as RFC 9457 problem+json by
  the shared exception handler when the handle is unknown.

Both paths sit outside the ``/roadmaps`` prefix, so they live on their own router
(mounted on the external app only, alongside accounts/OAuth). The service is
injected via ``service_provider`` so production binds a request-scoped DB session
while tests substitute an in-memory-backed service.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends

from wren.core.identity import require_user
from wren.roadmaps.list_schemas import Dashboard, Profile
from wren.roadmaps.listing import ListingService

# A FastAPI dependency that yields a ListingService for the request.
ListingServiceProvider = Callable[..., object]


def create_listing_router(service_provider: ListingServiceProvider) -> APIRouter:
    """Build the dashboard + profile router, injecting the service provider."""
    router = APIRouter(tags=["listing"])

    @router.get("/me/dashboard")
    async def get_dashboard(
        user_id: str = Depends(require_user),
        service: ListingService = Depends(service_provider),
    ) -> Dashboard:
        # Private, caller-scoped: everything the caller authored (any status) plus
        # everything they follow (spec section 02 US-ACCT-03).
        return await service.dashboard(user_id)

    @router.get("/users/{handle}")
    async def get_profile(
        handle: str,
        service: ListingService = Depends(service_provider),
    ) -> Profile:
        # Public + viewer-agnostic: the handle owner's published-public roadmaps
        # only; an unknown handle is a 404 via the shared exception handler. No
        # session is required or consulted, so drafts/private/archived and the
        # social graph are never exposed.
        return await service.profile(handle)

    return router
