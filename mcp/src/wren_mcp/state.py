"""Typed accessors for the RS's ``app.state`` / ``request.state`` seams.

Starlette's ``app.state`` and ``request.state`` are dynamically typed: attribute
access launders to ``Any``, which silently bypasses ``mypy --strict`` at the
wiring and auth perimeter (a renamed seam is not caught statically). This module
is the one typed place those seams are read and written:

- :class:`RsDeps` is the frozen façade over the three injected dependencies the
  RS exposes on ``app.state`` (the JWKS key provider, the bearer verifier, and
  the internal-API client). :func:`set_rs_deps` / :func:`get_rs_deps` store and
  read it under a single typed key.
- :func:`get_request_agent` / :func:`set_request_agent` centralize the
  ``getattr`` + ``isinstance`` guard for the resolved principal the bearer
  boundary stashes on ``request.state``, so a tool reached without the guard
  fails closed (``None``) rather than laundering an ``Any`` through the gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from wren_mcp.tokens import AgentTokenVerifier, VerifiedAgentToken

if TYPE_CHECKING:
    from starlette.applications import Starlette
    from starlette.requests import Request

    from wren_mcp.client import InternalApiClient
    from wren_mcp.keys import KeyProvider

# One app.state key holds the whole dependency façade; one request.state key holds
# the per-request resolved principal.
RS_DEPS_ATTR = "rs_deps"
AGENT_STATE_ATTR = "agent"


@dataclass(frozen=True)
class RsDeps:
    """The injected seams the RS wiring exposes on ``app.state``.

    Constructed once in :func:`wren_mcp.app.create_rs_app` and stored via
    :func:`set_rs_deps`; the dataclass makes the three seams a checked contract
    instead of three untyped ``app.state`` writes."""

    key_provider: KeyProvider
    token_verifier: AgentTokenVerifier
    internal_client: InternalApiClient


def set_rs_deps(app: Starlette, deps: RsDeps) -> None:
    """Store the RS dependency façade on ``app.state`` under one typed key."""
    setattr(app.state, RS_DEPS_ATTR, deps)


def get_rs_deps(app: Starlette) -> RsDeps:
    """Return the RS dependency façade, or raise if the app was never wired.

    Unlike the auth-boundary accessors this has no fail-safe default: the deps are
    set at app construction, so their absence is a wiring bug, not a runtime input
    to tolerate."""
    deps = getattr(app.state, RS_DEPS_ATTR, None)
    if not isinstance(deps, RsDeps):
        raise RuntimeError("RS dependencies are not configured on app.state.")
    return deps


def set_request_agent(request: Request, principal: VerifiedAgentToken) -> None:
    """Stash the resolved principal on ``request.state`` (never the raw token)."""
    setattr(request.state, AGENT_STATE_ATTR, principal)


def get_request_agent(request: Request | None) -> VerifiedAgentToken | None:
    """Return the principal the bearer boundary resolved, or ``None``.

    Returns ``None`` on a missing request, a missing attribute, OR a wrong-type
    value, so a tool reached without the guard middleware fails closed rather than
    trusting an unchecked ``app.state`` value."""
    if request is None:
        return None
    principal = getattr(request.state, AGENT_STATE_ATTR, None)
    return principal if isinstance(principal, VerifiedAgentToken) else None
