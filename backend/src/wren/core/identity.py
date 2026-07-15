"""Identity resolution at the two trust boundaries.

Every request resolves to exactly one ``user_id``; the server never trusts a
``user_id`` from request/tool args for authorization. The two apps resolve that
identity differently, and this module is the single place that difference lives:

- **External (:8000)** authenticates humans by a signed-JWT session cookie and
  **strips any client-supplied ``X-User-ID``** (via
  :class:`StripInboundIdentityMiddleware`, wired app-wide) so a spoofed header can
  never reach a handler. Cookie verification is injected as a
  :data:`SessionVerifier`; Ticket 6 supplies the real JWT logic through this same
  contract without reworking the seam.
- **Internal (:8001)** **trusts ``X-User-ID``** and additionally requires the
  shared ``INTERNAL_API_TOKEN`` header as defense-in-depth behind ``compute-net``
  network isolation.

These are FastAPI dependencies; later route slices declare
``Depends(require_user)`` / ``Depends(require_internal_user)``.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from wren.core.errors import Unauthorized

USER_ID_HEADER = "X-User-ID"
INTERNAL_TOKEN_HEADER = "X-Internal-Api-Token"
SESSION_COOKIE_NAME = "wren_session"

# A SessionVerifier turns a raw session-cookie value into a resolved user_id, or
# None if the cookie is missing/invalid/expired. It is async so Ticket 6 can add a
# per-request jti-blacklist lookup (an I/O call) behind this same contract without
# reworking require_user.
SessionVerifier = Callable[[str], Awaitable[str | None]]


async def deny_all_sessions(_cookie: str) -> str | None:
    """Default verifier until Ticket 6 issues sessions: every cookie fails to
    resolve, so :func:`require_user` fail-safe denies. Replaced by injecting a
    real ``SessionVerifier`` on ``app.state.session_verifier``."""
    return None


class StripInboundIdentityMiddleware:
    """Remove client-supplied identity headers before the external app routes.

    Wired on the external app only. A spoofed ``X-User-ID`` from the internet is
    dropped here, app-wide, so it can never reach a handler or be mistaken for a
    resolved identity: the strip is a boundary guarantee, not something each route
    must remember. The internal app deliberately does *not* wire this: it trusts
    ``X-User-ID`` and is unreachable from the internet by construction.
    """

    def __init__(self, app: ASGIApp, *, header: str = USER_ID_HEADER) -> None:
        self.app = app
        # ASGI header names arrive lower-cased as latin-1 bytes.
        self._blocked = header.lower().encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            kept = [
                (name, value) for name, value in scope["headers"] if name.lower() != self._blocked
            ]
            scope = {**scope, "headers": kept}
        await self.app(scope, receive, send)


async def require_user(request: Request) -> str:
    """External dependency: resolve ``user_id`` from the session cookie.

    Reads only the cookie; ``X-User-ID`` is never consulted (and is stripped
    upstream by :class:`StripInboundIdentityMiddleware`). Raises ``Unauthorized``
    when no valid session resolves.
    """
    verify: SessionVerifier = getattr(request.app.state, "session_verifier", deny_all_sessions)
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie is None:
        raise Unauthorized("No session cookie present.")
    user_id = await verify(cookie)
    if user_id is None:
        raise Unauthorized("Session is invalid or expired.")
    return user_id


async def require_internal_user(request: Request) -> str:
    """Internal dependency: trust ``X-User-ID`` behind a valid ``INTERNAL_API_TOKEN``.

    The shared token gates the internal surface as defense-in-depth; a missing or
    unconfigured token fail-safe denies. Only then is the trusted ``X-User-ID``
    taken as the resolved identity.
    """
    expected: str = getattr(request.app.state, "internal_api_token", "")
    supplied = request.headers.get(INTERNAL_TOKEN_HEADER)
    # Compare on encoded bytes: secrets.compare_digest raises TypeError on a
    # non-ASCII str, which would surface as a 500 instead of a clean 401.
    if (
        not expected
        or supplied is None
        or not secrets.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))
    ):
        raise Unauthorized("Missing or invalid internal API token.")
    user_id = request.headers.get(USER_ID_HEADER)
    if not user_id:
        raise Unauthorized("Missing trusted X-User-ID header.")
    return user_id
