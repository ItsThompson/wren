"""Periodic sweep that reaps stale open-registration OAuth clients.

Wires the P0 cleanup hook
(:meth:`wren.oauth.token_exchange.TokenService.cleanup_stale_clients`) to a
background task the external app starts on its lifespan. Without this the Dynamic
Client Registration rows (RFC 7591 open registration) grow unbounded, because
nothing else invokes the sweep.

The sweep reaps by registration age (``OAuthClient.created_at``), cascade-revoking
each reaped client's grant + refresh chain in one transaction. It runs on its own
short-lived session from the app's session factory, independent of any request.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import timedelta
from typing import TYPE_CHECKING

from wren.core.logging import get_logger
from wren.oauth.wiring import build_token_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from wren.oauth.config import OAuthConfig
    from wren.oauth.tokens import AccessTokenCodec

_log = get_logger("wren-oauth-cleanup")

# A one-shot reap: returns the number of stale clients deleted.
Sweep = Callable[[], Awaitable[int]]


def build_stale_client_sweep(
    sessionmaker: async_sessionmaker[AsyncSession],
    config: OAuthConfig,
    codec: AccessTokenCodec,
    *,
    max_age: timedelta,
) -> Sweep:
    """Build the one-shot sweep: open a session and reap clients older than ``max_age``."""

    async def sweep() -> int:
        async with sessionmaker() as session:
            service = build_token_service(session, config, codec)
            return await service.cleanup_stale_clients(older_than=max_age)

    return sweep


async def run_cleanup_loop(sweep: Sweep, *, interval: timedelta) -> None:
    """Run ``sweep`` once per ``interval``, forever, until cancelled.

    Sleeps first so app startup is never blocked on a sweep. A sweep failure is
    logged and the loop continues: a transient DB error must not kill the reaper.
    Cancellation propagates so the lifespan can stop the task cleanly.
    """
    interval_seconds = interval.total_seconds()
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            deleted = await sweep()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad sweep must not kill the reaper
            _log.error("oauth_client_cleanup_failed", exc_info=exc)
        else:
            _log.info("oauth_client_cleanup_swept", deleted=deleted)


def start_stale_client_cleanup(
    sessionmaker: async_sessionmaker[AsyncSession],
    config: OAuthConfig,
    codec: AccessTokenCodec,
    *,
    interval: timedelta,
    max_age: timedelta,
) -> asyncio.Task[None] | None:
    """Start the periodic reaper as a background task.

    Returns the task, or ``None`` when disabled (a non-positive ``interval``), so
    an environment that reaps out of band can turn the in-process sweep off.
    """
    if interval <= timedelta(0):
        _log.info("oauth_client_cleanup_disabled")
        return None
    sweep = build_stale_client_sweep(sessionmaker, config, codec, max_age=max_age)
    return asyncio.create_task(
        run_cleanup_loop(sweep, interval=interval), name="oauth-client-cleanup"
    )


async def stop_stale_client_cleanup(task: asyncio.Task[None] | None) -> None:
    """Cancel and await the reaper task (a no-op when it was disabled)."""
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
