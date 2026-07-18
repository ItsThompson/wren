"""Best-effort Discord notification on a successful registration.

A small seam injected into :class:`~wren.accounts.service.AccountService` exactly
like the password hasher and token codec. ``user_registered`` is fire-and-forget:
it schedules delivery on the event loop and returns synchronously, so it never
blocks, slows, or fails the registration request. All I/O and every error live
inside the background task; the public method cannot raise into ``register``
(which is ``@track_failures``-wrapped, so an escaping exception would both fail
the signup and count a spurious service-method failure).

Two implementations: :class:`NullRegistrationNotifier` (the default, used when no
webhook is configured) and :class:`DiscordRegistrationNotifier` (the real POST).
The webhook is held as ``SecretStr`` and the failure path logs only a coarse
category (``error_type``/``status``), never ``str(exc)``, the exception object,
or ``exc_info`` -- an httpx exception string embeds the request URL, so rendering
it (or a traceback) would leak the webhook.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

import httpx

from wren.core.logging import get_logger

if TYPE_CHECKING:
    from pydantic import SecretStr

_log = get_logger("wren-accounts")

# The default per-notification timeout (connect + read + write + pool), in
# seconds. Signup volume is low, so a short-lived client per call is cheaper to
# reason about than shared-client lifecycle wiring.
_DEFAULT_TIMEOUT = 5.0


class RegistrationNotifier(Protocol):
    """Announces a new signup. Implementations MUST NOT raise or block register."""

    def user_registered(self, *, username: str, user_id: str) -> None: ...


class NullRegistrationNotifier:
    """No-op notifier used when no webhook is configured (the fail-safe default)."""

    def user_registered(self, *, username: str, user_id: str) -> None:
        return

    async def aclose(self) -> None:
        return


class DiscordRegistrationNotifier:
    """Posts a signup announcement to a Discord Incoming Webhook, best-effort."""

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
        # Strong refs to in-flight deliveries so the event loop cannot GC a
        # pending task mid-flight; each task removes itself on completion.
        self._pending: set[asyncio.Task[None]] = set()

    def user_registered(self, *, username: str, user_id: str) -> None:
        """Schedule the announcement and return immediately (never blocks)."""
        content = f"🎉 New user registered: {username}"
        task = asyncio.create_task(self._deliver(content))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def aclose(self) -> None:
        """Await all in-flight deliveries (graceful-shutdown hook + test drain)."""
        await asyncio.gather(*self._pending, return_exceptions=True)

    async def _deliver(self, content: str) -> None:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    self._url.get_secret_value(), json={"content": content}
                )
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - best-effort: no delivery error may escape
            # Log only a coarse category. NEVER str(exc)/the exception object/
            # exc_info: an httpx error string (or a rendered traceback) embeds the
            # request URL and would leak the webhook.
            _log.warning(
                "discord_notify_failed",
                error_type=type(exc).__name__,
                status=getattr(getattr(exc, "response", None), "status_code", None),
            )
