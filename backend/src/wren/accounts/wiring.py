"""Compose the accounts dependency graph for the external app.

Keeps the wiring (which request-scoped session backs the repository) out of the
router and the entrypoint. The production service provider resolves a per-request
``AsyncSession`` via ``get_session`` and binds the SQLAlchemy repository; the
hasher and codec are process-wide singletons.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

from wren.accounts.notifications import (
    NULL_EVENT_PUBLISHER,
    BestEffortEventPublisher,
    DiscordUserRegisteredHandler,
    EventPublisher,
)
from wren.accounts.repository import SqlAlchemyAccountRepository
from wren.accounts.service import AccountService
from wren.core.db import get_session

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from wren.accounts.passwords import PasswordHasher
    from wren.accounts.tokens import SessionTokenCodec
    from wren.core.settings import AppSettings


def build_event_publisher(settings: AppSettings) -> EventPublisher:
    """Build process-wide event delivery for the external app.

    When no webhook is set the publisher is a null object. When Discord is
    configured, the best-effort publisher owns scheduling/error isolation and the
    Discord handler owns only message formatting + HTTP delivery.
    """
    if not settings.discord_webhook_url.get_secret_value():
        return NULL_EVENT_PUBLISHER
    return BestEffortEventPublisher([DiscordUserRegisteredHandler(settings.discord_webhook_url)])


def build_account_service_provider(
    hasher: PasswordHasher,
    codec: SessionTokenCodec,
    event_publisher: EventPublisher = NULL_EVENT_PUBLISHER,
) -> Callable[[AsyncSession], AccountService]:
    """A FastAPI dependency that builds a request-scoped :class:`AccountService`.

    ``event_publisher`` defaults to the null publisher, so callers that do not
    wire external delivery keep the event path inert.
    """

    def provider(session: AsyncSession = Depends(get_session)) -> AccountService:
        return AccountService(
            SqlAlchemyAccountRepository(session),
            hasher,
            codec,
            event_publisher=event_publisher,
        )

    return provider
