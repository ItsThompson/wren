"""The agent trust boundary: bearer validation on the MCP transport.

This is the RS's security perimeter. A pure-ASGI middleware guards the MCP
transport path prefix: every request under it must carry a valid
``Authorization: Bearer`` token (verified against the AS JWKS and audience-bound
to this RS). An invalid or missing token returns ``401`` with a
``WWW-Authenticate`` header pointing at the PRM document (RFC 9728), so a client
can discover the AS and authenticate. Guarding at the boundary (not per route) is
deliberate: a tool route mounted under the prefix cannot forget
to authenticate.

On success the resolved principal is stashed on ``request.state`` (never the raw
token, which is exchanged for an ``X-User-ID`` header downstream); the tool layer
reads it through :func:`wren_mcp.scopes.require_scope` (which resolves it via
:func:`wren_mcp.state.get_request_agent`), never from a tool argument.

The per-request correlation context is started app-wide by
:class:`wren_mcp.correlation.CorrelationMiddleware` (which mints the
``request_id``); once this boundary resolves the principal it binds ``user_id``
onto that context, so the tool-entry line and the internal-hop client all carry
the actor. A rejected bearer is logged at ``warning`` with a reason and never the
raw token.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse

from wren_mcp.logging import get_logger
from wren_mcp.prm import www_authenticate_challenge
from wren_mcp.settings import SERVICE
from wren_mcp.state import set_request_agent

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

    from wren_mcp.tokens import AgentTokenVerifier

_log = get_logger(SERVICE)

_BEARER_PREFIX = "Bearer "


def _extract_bearer(header_value: str | None) -> str | None:
    """Pull the token out of an ``Authorization: Bearer <token>`` header."""
    if header_value is None or not header_value.startswith(_BEARER_PREFIX):
        return None
    token = header_value[len(_BEARER_PREFIX) :].strip()
    return token or None


class BearerAuthMiddleware:
    """Requires a valid AS-issued bearer on the guarded MCP transport prefix."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        verifier: AgentTokenVerifier,
        resource: str,
        protected_prefix: str,
    ) -> None:
        self.app = app
        self._verifier = verifier
        self._resource = resource
        self._prefix = protected_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._is_protected(str(scope["path"])):
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        token = _extract_bearer(request.headers.get("authorization"))
        principal = await self._verifier.verify(token) if token is not None else None
        if principal is None:
            # Never log the raw token; no verified principal exists yet, so only a
            # reason is available (client_id/sub cannot be trusted pre-validation).
            _log.warning(
                "agent_token_rejected",
                reason="missing_bearer" if token is None else "invalid_token",
            )
            await self._challenge()(scope, receive, send)
            return
        # Boundary guarantee: the handler receives a resolved identity, never the
        # raw token. The token is exchanged for X-User-ID by the internal client.
        set_request_agent(request, principal)
        # Identity is resolved here, so bind the actor onto the app-wide
        # correlation context: this puts user_id on the tool-entry line
        # (tool_invoked). require_scope re-binds it idempotently at the tool layer.
        structlog.contextvars.bind_contextvars(user_id=principal.user_id)
        await self.app(scope, receive, send)

    def _is_protected(self, path: str) -> bool:
        return path == self._prefix or path.startswith(self._prefix + "/")

    def _challenge(self) -> JSONResponse:
        return JSONResponse(
            {"error": "invalid_token", "error_description": "A valid bearer token is required."},
            status_code=401,
            headers={"WWW-Authenticate": www_authenticate_challenge(self._resource)},
        )
