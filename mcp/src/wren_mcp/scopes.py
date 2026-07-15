"""Per-tool OAuth scope enforcement + agent identity resolution (spec section 08).

The bearer boundary (:mod:`wren_mcp.auth`) validates the token and stashes the
resolved :class:`~wren_mcp.tokens.VerifiedAgentToken` (carrying its ``sub`` and
granted ``scope``) on ``request.state`` before any tool runs. Every tool then
opens with :func:`require_scope`, which is the **one** way to obtain the request's
``user_id``: fusing identity resolution with the scope check means a tool cannot
be written that skips authorization, so the gate is enforced uniformly across the
write (Ticket 21) and read (Ticket 22) surfaces.

Scope semantics follow OAuth 2.1 (spec section 08): ``scope`` is a
space-delimited set of granted scopes. A token lacking the scope a tool requires
raises a **model-recoverable** :class:`ToolError` (``insufficient_scope``) naming
the missing scope, not a crash, so the agent can re-authorize and retry.
"""

from __future__ import annotations

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.session import ServerSession
from starlette.requests import Request

from wren_mcp.auth import AGENT_STATE_KEY
from wren_mcp.tokens import VerifiedAgentToken

# The Context the framework injects; the third param is the Starlette request
# carrying the identity the bearer boundary resolved onto ``request.state``.
AgentContext = Context[ServerSession, object, Request]


def _resolve_agent(ctx: AgentContext) -> VerifiedAgentToken:
    """Return the principal the bearer boundary resolved for this request.

    Fails closed with a :class:`ToolError` if the identity is somehow absent (a
    tool reached without the guard middleware), so a call can never run
    unauthenticated."""
    request = ctx.request_context.request
    principal = getattr(request.state, AGENT_STATE_KEY, None) if request is not None else None
    if not isinstance(principal, VerifiedAgentToken):
        raise ToolError("unauthenticated: no verified agent identity on the request.")
    return principal


def require_scope(ctx: AgentContext, *, scope: str) -> str:
    """Enforce that the request's token grants ``scope``; return its ``user_id``.

    This is the shared gate every tool opens with. Identity is resolved from the
    validated bearer (never a tool argument), the granted scope set is checked,
    and the single ``user_id`` the request is scoped to is returned. A missing
    scope raises a model-recoverable :class:`ToolError` the agent can act on."""
    principal = _resolve_agent(ctx)
    granted = set(principal.scope.split())
    if scope not in granted:
        have = principal.scope or "(none)"
        raise ToolError(
            f"insufficient_scope: this tool requires the '{scope}' OAuth scope, but the "
            f"token grants [{have}]. Re-authorize the agent with '{scope}' and retry."
        )
    return principal.user_id
