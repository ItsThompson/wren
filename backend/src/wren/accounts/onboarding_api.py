"""External REST adapter for onboarding completion: POST /me/onboarding:complete.

A single thin handler in its own small router so ``accounts/api.py`` stays focused
on ``/auth/*``. It resolves the caller's ``user_id`` via the injected ``identity``
dependency (``require_user`` on the external app), calls one
:class:`AccountService` method, and returns the updated :class:`AuthenticatedUser`;
the ``WrenError`` the service raises is rendered as RFC 9457 problem+json by the
shared exception handler.

The route takes no request body: the account to mark onboarded is always the
session-resolved identity, never a client-supplied id. It uses the ``/me``
namespace and the ``:action`` suffix style already used by
``POST /roadmaps/{id}:fork``, and is mounted on the external app only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends

from wren.accounts.schemas import AuthenticatedUser
from wren.accounts.service import AccountService

# A FastAPI dependency that resolves the request's ``user_id`` at the trust
# boundary (``require_user`` on the external app), injected so the router never
# hard-codes how identity is resolved.
Identity = Callable[..., Awaitable[str]]
# A FastAPI dependency that yields an AccountService for the request.
AccountServiceProvider = Callable[..., object]


def create_onboarding_router(
    service_provider: AccountServiceProvider, *, identity: Identity
) -> APIRouter:
    """Build the onboarding router, injecting the service provider and identity."""
    router = APIRouter(prefix="/me", tags=["onboarding"])

    @router.post("/onboarding:complete")
    async def complete(
        user_id: str = Depends(identity),
        service: AccountService = Depends(service_provider),
    ) -> AuthenticatedUser:
        # No request body: the account is the session-resolved identity only.
        return await service.complete_onboarding(user_id)

    return router
