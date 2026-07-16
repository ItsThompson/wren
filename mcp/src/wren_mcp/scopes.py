"""Per-tool OAuth scope enforcement + agent identity resolution.

The bearer boundary (:mod:`wren_mcp.auth`) validates the token and stashes the
resolved :class:`~wren_mcp.tokens.VerifiedAgentToken` (carrying its ``sub`` and
granted ``scope``) on ``request.state`` before any tool runs. Every tool then
opens with :func:`require_scope`, which is the **one** way to obtain the request's
``user_id``: fusing identity resolution with the scope check means a tool cannot
be written that skips authorization, so the gate is enforced uniformly across the
write and read surfaces.

Scope semantics follow OAuth 2.1: ``scope`` is a
space-delimited set of granted scopes. A token lacking the scope a tool requires
raises a **model-recoverable** :class:`ToolError` (``insufficient_scope``) naming
the missing scope, not a crash, so the agent can re-authorize and retry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.session import ServerSession
from starlette.requests import Request

from wren_mcp.logging import get_logger
from wren_mcp.settings import SERVICE
from wren_mcp.state import get_request_agent

if TYPE_CHECKING:
    from wren_mcp.tokens import VerifiedAgentToken

_log = get_logger(SERVICE)

# The Context the framework injects; the third param is the Starlette request
# carrying the identity the bearer boundary resolved onto ``request.state``.
AgentContext = Context[ServerSession, object, Request]


def _resolve_agent(ctx: AgentContext) -> VerifiedAgentToken:
    """Return the principal the bearer boundary resolved for this request.

    Fails closed with a :class:`ToolError` if the identity is somehow absent (a
    tool reached without the guard middleware), so a call can never run
    unauthenticated. Once resolved, binds ``user_id`` into contextvars so every
    subsequent line for this tool call carries it via ``merge_contextvars``."""
    request = ctx.request_context.request
    principal = get_request_agent(request)
    if principal is None:
        _log.warning("unauthenticated", reason="no_verified_identity")
        raise ToolError("unauthenticated: no verified agent identity on the request.")
    structlog.contextvars.bind_contextvars(user_id=principal.user_id)
    return principal


def require_scope(ctx: AgentContext, *, scope: str) -> str:
    """Enforce that the request's token grants ``scope``; return its ``user_id``.

    This is the shared gate every tool opens with. Identity is resolved from the
    validated bearer (never a tool argument), the granted scope set is checked,
    and the single ``user_id`` the request is scoped to is returned. A missing
    scope raises a model-recoverable :class:`ToolError` the agent can act on and
    is logged at ``warning`` (never the raw token)."""
    principal = _resolve_agent(ctx)
    granted = set(principal.scope.split())
    if scope not in granted:
        have = principal.scope or "(none)"
        _log.warning(
            "insufficient_scope",
            reason="missing_required_scope",
            required=scope,
            client_id=principal.client_id,
        )
        raise ToolError(
            f"insufficient_scope: this tool requires the '{scope}' OAuth scope, but the "
            f"token grants [{have}]. Re-authorize the agent with '{scope}' and retry."
        )
    return principal.user_id
