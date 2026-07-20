"""Identity resolution at the two trust boundaries.

Every request resolves to exactly one ``user_id``; the server never trusts a
``user_id`` from request/tool args for authorization. The two apps resolve that
identity differently, and this module is the single place that difference lives:

- **External (:8000)** authenticates humans by a signed-JWT session cookie and
  **strips any client-supplied ``X-User-ID``** (via
  :class:`StripInboundIdentityMiddleware`, wired app-wide) so a spoofed header can
  never reach a handler. Cookie verification is injected as a
  :data:`SessionVerifier`, so the real JWT logic is supplied through this same
  contract without reworking the seam.
- **Internal (:8001)** **trusts ``X-User-ID``** and additionally requires the
  shared ``INTERNAL_API_TOKEN`` header as the primary boundary on the internal
  app (non-tunnel-routed, non-host-published on ``app-net``).

These are FastAPI dependencies; route modules declare
``Depends(require_user)`` / ``Depends(require_internal_user)``.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

import structlog

# ``require_user`` / ``require_internal_user`` are FastAPI dependencies (not
# decorated route handlers, so runtime-evaluated-decorators does not reach them);
# FastAPI resolves their ``Request`` annotation at runtime, so it must stay a
# runtime import or FastAPI mistakes ``request`` for a query field.
from starlette.requests import Request  # noqa: TC002

from wren.core.errors import Unauthorized
from wren.core.state import SessionVerifier, get_internal_token, get_session_verifier
from wren_common.logging import get_logger

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

_log = get_logger("wren-core")

USER_ID_HEADER = "X-User-ID"
INTERNAL_TOKEN_HEADER = "X-Internal-Api-Token"
SESSION_COOKIE_NAME = "wren_session"


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
    verify: SessionVerifier = get_session_verifier(request.app)
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie is None:
        _log.warning("session_invalid", reason="missing_cookie")
        raise Unauthorized("No session cookie present.")
    user_id = await verify(cookie)
    if user_id is None:
        _log.warning("session_invalid", reason="invalid_or_expired")
        raise Unauthorized("Session is invalid or expired.")
    # Bind the resolved actor so every subsequent line for this request carries
    # user_id via merge_contextvars; retires the per-call-site actor kwarg.
    structlog.contextvars.bind_contextvars(user_id=user_id)
    return user_id


async def require_internal_user(request: Request) -> str:
    """Internal dependency: trust ``X-User-ID`` behind a valid ``INTERNAL_API_TOKEN``.

    The shared token gates the internal surface as defense-in-depth; a missing or
    unconfigured token fail-safe denies. Only then is the trusted ``X-User-ID``
    taken as the resolved identity.
    """
    expected = get_internal_token(request.app)
    supplied = request.headers.get(INTERNAL_TOKEN_HEADER)
    # Unwrap the SecretStr once here, the single use site; the raw value never
    # leaves this comparison (it is never logged). Compare on encoded bytes:
    # secrets.compare_digest raises TypeError on a non-ASCII str, which would
    # surface as a 500 instead of a clean 401.
    expected_value = expected.get_secret_value()
    if (
        not expected_value
        or supplied is None
        or not secrets.compare_digest(supplied.encode("utf-8"), expected_value.encode("utf-8"))
    ):
        _log.warning("internal_token_rejected", reason="missing_or_invalid_token")
        raise Unauthorized("Missing or invalid internal API token.")
    user_id = request.headers.get(USER_ID_HEADER)
    if not user_id:
        _log.warning("internal_token_rejected", reason="missing_user_id")
        raise Unauthorized("Missing trusted X-User-ID header.")
    structlog.contextvars.bind_contextvars(user_id=user_id)
    return user_id
