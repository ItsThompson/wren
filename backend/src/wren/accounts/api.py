"""External REST adapter for accounts: /auth/register, /login, /refresh, /logout.

Thin handlers: each maps one request to one
:class:`AccountService` call, writes or clears the session cookies, and returns
the authenticated user (never the password hash). The ``WrenError`` the service
raises is rendered as RFC 9457 problem+json by the shared exception handler.

The service is injected via ``service_provider`` (a FastAPI dependency) so the
production binding resolves a request-scoped DB session while tests substitute an
in-memory-backed service. These routes are mounted on the external app only.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, Request, Response

from wren.accounts.config import AUTH_PATH, REFRESH_COOKIE_NAME, CookieConfig
from wren.accounts.schemas import AuthenticatedUser, LoginRequest, RegisterRequest
from wren.accounts.service import AccountService
from wren.accounts.tokens import TokenPair
from wren.core.errors import Unauthorized
from wren.core.identity import SESSION_COOKIE_NAME

# A FastAPI dependency that yields an AccountService for the request.
AccountServiceProvider = Callable[..., object]


def create_accounts_router(
    service_provider: AccountServiceProvider, *, cookie_config: CookieConfig
) -> APIRouter:
    """Build the /auth router, injecting the service provider and cookie policy."""
    router = APIRouter(prefix=AUTH_PATH, tags=["auth"])

    @router.post("/register", status_code=201)
    async def register(
        body: RegisterRequest,
        response: Response,
        service: AccountService = Depends(service_provider),
    ) -> AuthenticatedUser:
        session = await service.register(body.username, body.email, body.password)
        _write_session_cookies(response, session.tokens, cookie_config)
        return session.user

    @router.post("/login")
    async def login(
        body: LoginRequest,
        response: Response,
        service: AccountService = Depends(service_provider),
    ) -> AuthenticatedUser:
        session = await service.login(body.email, body.password)
        _write_session_cookies(response, session.tokens, cookie_config)
        return session.user

    @router.post("/refresh")
    async def refresh(
        request: Request,
        response: Response,
        service: AccountService = Depends(service_provider),
    ) -> AuthenticatedUser:
        token = request.cookies.get(REFRESH_COOKIE_NAME)
        if token is None:
            raise Unauthorized("No refresh token present.")
        session = await service.refresh(token)
        _write_session_cookies(response, session.tokens, cookie_config)
        return session.user

    @router.post("/logout", status_code=204)
    async def logout(
        request: Request,
        response: Response,
        service: AccountService = Depends(service_provider),
    ) -> None:
        await service.logout(request.cookies.get(REFRESH_COOKIE_NAME))
        _clear_session_cookies(response, cookie_config)

    return router


def _write_session_cookies(response: Response, tokens: TokenPair, config: CookieConfig) -> None:
    """Set the access cookie (site-wide) and refresh cookie (scoped to /auth)."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=tokens.access_token,
        max_age=tokens.access_max_age,
        httponly=True,
        secure=config.secure,
        samesite=config.samesite,
        domain=config.domain,
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=tokens.refresh_token,
        max_age=tokens.refresh_max_age,
        httponly=True,
        secure=config.secure,
        samesite=config.samesite,
        domain=config.domain,
        path=AUTH_PATH,
    )


def _clear_session_cookies(response: Response, config: CookieConfig) -> None:
    """Expire both cookies with the same attributes they were written with."""
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        domain=config.domain,
        secure=config.secure,
        httponly=True,
        samesite=config.samesite,
    )
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=AUTH_PATH,
        domain=config.domain,
        secure=config.secure,
        httponly=True,
        samesite=config.samesite,
    )
