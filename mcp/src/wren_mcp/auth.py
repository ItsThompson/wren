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
token, which is exchanged for an ``X-User-ID`` header downstream); handlers read
it via :func:`agent_identity`.

This is also where an agent action's correlation context begins: on entry to the
guarded transport the middleware clears any leftover contextvars and binds a
fresh ``request_id``, so the tool layer, the internal-hop client, and the backend
all share one id (``merge_contextvars`` attaches it to every line). A rejected
bearer is logged at ``warning`` with a reason and never the raw token.
"""

from __future__ import annotations

from uuid import uuid4

import structlog
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from wren_mcp.logging import get_logger
from wren_mcp.prm import www_authenticate_challenge
from wren_mcp.settings import SERVICE
from wren_mcp.tokens import AgentTokenVerifier, VerifiedAgentToken

_log = get_logger(SERVICE)

_BEARER_PREFIX = "Bearer "
# Key the resolved principal is stashed under on request.state.
AGENT_STATE_KEY = "agent"


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
        # An agent action enters here: start its correlation context (clear first
        # so a reused worker context cannot leak a prior request's bindings) so
        # the tool layer, the internal-hop client, and the backend share one id.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=uuid4().hex)
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
        request.state.agent = principal
        await self.app(scope, receive, send)

    def _is_protected(self, path: str) -> bool:
        return path == self._prefix or path.startswith(self._prefix + "/")

    def _challenge(self) -> JSONResponse:
        return JSONResponse(
            {"error": "invalid_token", "error_description": "A valid bearer token is required."},
            status_code=401,
            headers={"WWW-Authenticate": www_authenticate_challenge(self._resource)},
        )


def agent_identity(request: Request) -> VerifiedAgentToken:
    """Return the principal resolved by the boundary middleware.

    Handlers mounted under the guarded prefix depend on this to
    get the single ``user_id`` the request is scoped to. Fails closed with 401 if
    it is ever reached without the middleware having set the principal (a route
    mounted outside the guarded prefix), so identity can never be silently absent.
    """
    principal = getattr(request.state, AGENT_STATE_KEY, None)
    if not isinstance(principal, VerifiedAgentToken):
        raise HTTPException(status_code=401, detail="Unauthenticated.")
    return principal
