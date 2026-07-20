"""Compose the OAuth AS dependency graph for the external app.

Keeps wiring (which request-scoped session backs the repository) out of the
router and entrypoint. The signing key set and access-token codec are process-wide
singletons; the service providers resolve a per-request ``AsyncSession`` via
``get_session`` and bind the SQLAlchemy repository, mirroring the accounts wiring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

from wren.core.db import get_session
from wren.oauth.authorization import AuthorizationService
from wren.oauth.repository import SqlAlchemyOAuthRepository
from wren.oauth.token_exchange import TokenService

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from wren.oauth.config import OAuthConfig
    from wren.oauth.tokens import AccessTokenCodec


def build_authorization_service_provider(
    config: OAuthConfig,
) -> Callable[[AsyncSession], AuthorizationService]:
    """A FastAPI dependency that builds a request-scoped :class:`AuthorizationService`."""

    def provider(session: AsyncSession = Depends(get_session)) -> AuthorizationService:
        return AuthorizationService(SqlAlchemyOAuthRepository(session), config)

    return provider


def build_token_service(
    session: AsyncSession, config: OAuthConfig, codec: AccessTokenCodec
) -> TokenService:
    """Bind a :class:`TokenService` over a session.

    Shared by the request-scoped provider and the background client-cleanup sweep
    (:mod:`wren.oauth.cleanup`), so the two never diverge in how the service is
    composed.
    """
    return TokenService(SqlAlchemyOAuthRepository(session), config, codec)


def build_token_service_provider(
    config: OAuthConfig, codec: AccessTokenCodec
) -> Callable[[AsyncSession], TokenService]:
    """A FastAPI dependency that builds a request-scoped :class:`TokenService`."""

    def provider(session: AsyncSession = Depends(get_session)) -> TokenService:
        return build_token_service(session, config, codec)

    return provider
