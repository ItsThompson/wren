"""Best-effort notification delivery for user-registration events.

The account service emits an explicit, fully validated event after durable user
creation. Delivery policy lives here at the edge: configured handlers are
scheduled best-effort, failures are swallowed inside background tasks, and secret
material is never rendered into logs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import httpx

from wren_common.logging import get_logger

if TYPE_CHECKING:
    from pydantic import SecretStr

_log = get_logger("wren-accounts")

# The default per-notification timeout (connect + read + write + pool), in
# seconds. Signup volume is low, so a short-lived client per event is cheaper to
# reason about than shared-client lifecycle wiring.
_DEFAULT_TIMEOUT = 5.0


@dataclass(frozen=True, slots=True)
class UserRegistered:
    """A user was durably created and can now be announced to external systems."""

    user_id: str
    username: str


class EventPublisher(Protocol):
    """Publishes user-registration events without raising into the caller."""

    def publish(self, event: UserRegistered) -> None: ...

    async def aclose(self) -> None: ...


class UserRegisteredHandler(Protocol):
    """Handles user-registration events. Failures are owned by the publisher."""

    async def handle(self, event: UserRegistered) -> None: ...


class NullEventPublisher:
    """No-op publisher used when no external event handlers are configured."""

    def publish(self, event: UserRegistered) -> None:
        return

    async def aclose(self) -> None:
        return


NULL_EVENT_PUBLISHER = NullEventPublisher()


class BestEffortEventPublisher:
    """Schedules handler delivery and keeps delivery failures out of core flows."""

    def __init__(self, handlers: list[UserRegisteredHandler]) -> None:
        self._handlers = handlers
        # Strong refs to in-flight deliveries so the event loop cannot GC a
        # pending task mid-flight; each task removes itself on completion.
        self._pending: set[asyncio.Task[None]] = set()

    def publish(self, event: UserRegistered) -> None:
        task = asyncio.create_task(self._deliver(event))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def aclose(self) -> None:
        """Await in-flight deliveries for graceful shutdown and deterministic tests."""
        await asyncio.gather(*self._pending, return_exceptions=True)

    async def _deliver(self, event: UserRegistered) -> None:
        for handler in self._handlers:
            try:
                await handler.handle(event)
            except Exception as exc:  # noqa: BLE001 - best-effort delivery boundary
                # Log only coarse failure metadata. NEVER str(exc), the exception
                # object, or exc_info: handler exception strings and tracebacks can
                # embed secret-bearing URLs or payloads.
                _log.warning(
                    "event_delivery_failed",
                    event_type=type(event).__name__,
                    handler=type(handler).__name__,
                    user_id=event.user_id,
                    error_type=type(exc).__name__,
                    status=getattr(getattr(exc, "response", None), "status_code", None),
                )


class DiscordUserRegisteredHandler:
    """Posts a signup announcement to a Discord Incoming Webhook."""

    def __init__(
        self,
        webhook_url: SecretStr,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = webhook_url
        self._timeout = timeout
        # A test seam: httpx.MockTransport in tests exercises the real POST path
        # without a live network; None uses httpx's default transport.
        self._transport = transport

    async def handle(self, event: UserRegistered) -> None:
        content = f"🎉 New user registered: {event.username}"
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(self._url.get_secret_value(), json={"content": content})
            response.raise_for_status()
