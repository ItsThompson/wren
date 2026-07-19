"""Typed accessors for the RS's ``app.state`` / ``request.state`` seams.

:class:`RsDeps` is the typed façade over the three injected ``app.state`` seams;
the request accessor centralizes the ``getattr`` + ``isinstance`` for the resolved
principal so a tool reached without the guard fails closed. Exercised against real
Starlette app/request state (the datastructures :mod:`wren_mcp.app` and
:mod:`wren_mcp.scopes` read through)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from starlette.applications import Starlette
from starlette.requests import Request

from wren_mcp.state import (
    AGENT_STATE_ATTR,
    RsDeps,
    get_request_agent,
    get_rs_deps,
    set_request_agent,
    set_rs_deps,
)

if TYPE_CHECKING:
    from wren_mcp.client import InternalApiClient
    from wren_mcp.keys import KeyProvider
    from wren_mcp.tokens import AgentTokenVerifier
from wren_mcp.tokens import VerifiedAgentToken


def _deps() -> RsDeps:
    # The accessor only checks the façade's identity/type, not the field types, so
    # opaque sentinels stand in for the three injected seams here.
    return RsDeps(
        key_provider=cast("KeyProvider", object()),
        token_verifier=cast("AgentTokenVerifier", object()),
        internal_client=cast("InternalApiClient", object()),
    )


def _request() -> Request:
    return Request({"type": "http", "headers": [], "method": "POST", "path": "/mcp"})


# --- RsDeps (app.state façade) ----------------------------------------------


def test_get_rs_deps_returns_the_stored_facade() -> None:
    app = Starlette()
    deps = _deps()
    set_rs_deps(app, deps)
    assert get_rs_deps(app) is deps


def test_get_rs_deps_raises_when_the_app_was_never_wired() -> None:
    # No fail-safe default: absence of the deps is a wiring bug, not a runtime
    # input to tolerate.
    with pytest.raises(RuntimeError):
        get_rs_deps(Starlette())


# --- request.state.agent accessor -------------------------------------------


def test_get_request_agent_returns_the_stashed_principal() -> None:
    principal = VerifiedAgentToken(user_id="user-ada", client_id="agent", scope="roadmaps:read")
    request = _request()
    set_request_agent(request, principal)
    assert get_request_agent(request) is principal


def test_get_request_agent_is_none_without_a_request() -> None:
    assert get_request_agent(None) is None


def test_get_request_agent_is_none_when_unset() -> None:
    assert get_request_agent(_request()) is None


def test_get_request_agent_fails_closed_on_a_wrong_type() -> None:
    # A non-principal value on the seam must never be trusted as identity.
    request = _request()
    setattr(request.state, AGENT_STATE_ATTR, "not-a-principal")
    assert get_request_agent(request) is None
