"""External REST adapter for the dashboard and public profile.

Thin handlers over:class:`ListingService`:

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

from wren.core.route_registry import App, identity_for_app
from wren.roadmaps.list_schemas import Dashboard, Profile
from wren.roadmaps.listing import ListingService

# A FastAPI dependency that yields a ListingService for the request.
ListingServiceProvider = Callable[..., object]


def create_listing_router(
    service_provider: ListingServiceProvider, *, app: App = App.EXTERNAL
) -> APIRouter:
    """Build the dashboard + profile router for one app trust boundary."""
    router = APIRouter(tags=["listing"])
    identity = identity_for_app(app)

    @router.get("/me/dashboard")
    async def get_dashboard(
        user_id: str = Depends(identity),
        service: ListingService = Depends(service_provider),
    ) -> Dashboard:
        # Private, caller-scoped: everything the caller authored (any status) plus
        # everything they follow.
        return await service.dashboard(user_id)

    async def get_profile(
        handle: str,
        service: ListingService = Depends(service_provider),
    ) -> Profile:
        # The internal route is authenticated at the trusted boundary even though
        # the projection itself is viewer-agnostic and public on the external app.
        return await service.profile(handle)

    router.add_api_route(
        "/users/{handle}",
        get_profile,
        methods=["GET"],
        dependencies=[Depends(identity)] if app is App.INTERNAL else None,
    )

    return router
