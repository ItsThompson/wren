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
    DiscordRegistrationNotifier,
    NullRegistrationNotifier,
    RegistrationNotifier,
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


def build_registration_notifier(settings: AppSettings) -> RegistrationNotifier:
    """Discord notifier when a webhook is configured, else the no-op Null notifier.

    Built once at boot (a process-wide singleton) so the concrete Discord notifier
    owns a single in-flight-task set across every request. When no webhook is set
    the notification path is inert (AC5).
    """
    if settings.discord_webhook_url.get_secret_value():
        return DiscordRegistrationNotifier(settings.discord_webhook_url)
    return NullRegistrationNotifier()


def build_account_service_provider(
    hasher: PasswordHasher,
    codec: SessionTokenCodec,
    notifier: RegistrationNotifier | None = None,
) -> Callable[[AsyncSession], AccountService]:
    """A FastAPI dependency that builds a request-scoped :class:`AccountService`.

    ``notifier`` defaults to the no-op Null notifier (via a None sentinel that
    ``AccountService`` resolves), so callers that do not wire a notifier -- the
    existing 2-arg call sites -- keep the notification path inert.
    """

    def provider(session: AsyncSession = Depends(get_session)) -> AccountService:
        return AccountService(
            SqlAlchemyAccountRepository(session), hasher, codec, notifier=notifier
        )

    return provider
