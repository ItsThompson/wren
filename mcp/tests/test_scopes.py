"""Unit tests for the shared scope gate + identity resolution.

:func:`wren_mcp.scopes.require_scope` is the single gate every write and read tool
opens with: it resolves the request's identity from the bearer the boundary
stashed on ``request.state`` (never a tool argument) and enforces the required
OAuth scope, returning the ``user_id``. These tests exercise it directly, off the
transport, mirroring the fast identity-guard checks the tool tests can't isolate.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from starlette.requests import Request

from wren_mcp.auth import AGENT_STATE_KEY
from wren_mcp.config import SCOPE_PROGRESS_WRITE, SCOPE_ROADMAPS_READ, SCOPE_ROADMAPS_WRITE
from wren_mcp.scopes import require_scope
from wren_mcp.tokens import VerifiedAgentToken


def _ctx_with(request: Request | None) -> SimpleNamespace:
    return SimpleNamespace(request_context=SimpleNamespace(request=request))


def _request_with_agent(principal: object) -> Request:
    request = Request({"type": "http", "headers": [], "method": "POST", "path": "/mcp"})
    setattr(request.state, AGENT_STATE_KEY, principal)
    return request


def _agent(scope: str) -> VerifiedAgentToken:
    return VerifiedAgentToken(user_id="user-ada", client_id="agent", scope=scope)


def test_require_scope_returns_user_id_when_the_scope_is_granted() -> None:
    ctx = _ctx_with(_request_with_agent(_agent("roadmaps:read roadmaps:write")))
    assert require_scope(ctx, scope=SCOPE_ROADMAPS_READ) == "user-ada"
    assert require_scope(ctx, scope=SCOPE_ROADMAPS_WRITE) == "user-ada"


def test_require_scope_rejects_a_token_missing_the_required_scope() -> None:
    # A read-only token cannot drive a progress:write tool.
    ctx = _ctx_with(_request_with_agent(_agent("roadmaps:read")))
    with pytest.raises(ToolError) as excinfo:
        require_scope(ctx, scope=SCOPE_PROGRESS_WRITE)
    message = str(excinfo.value)
    assert "insufficient_scope" in message
    assert SCOPE_PROGRESS_WRITE in message


def test_require_scope_matches_whole_scopes_not_substrings() -> None:
    # "roadmaps:write" must not be satisfied by a token that only grants
    # "roadmaps:read" even though one is a prefix of neither: the scope set is
    # split on whitespace and compared by exact membership.
    ctx = _ctx_with(_request_with_agent(_agent("roadmaps:read")))
    with pytest.raises(ToolError):
        require_scope(ctx, scope=SCOPE_ROADMAPS_WRITE)


def test_require_scope_reports_none_when_the_token_grants_no_scope() -> None:
    ctx = _ctx_with(_request_with_agent(_agent("")))
    with pytest.raises(ToolError) as excinfo:
        require_scope(ctx, scope=SCOPE_ROADMAPS_READ)
    assert "(none)" in str(excinfo.value)


def test_require_scope_fails_closed_when_identity_is_absent() -> None:
    bare = Request({"type": "http", "headers": [], "method": "POST", "path": "/mcp"})
    with pytest.raises(ToolError):
        require_scope(_ctx_with(bare), scope=SCOPE_ROADMAPS_READ)


def test_require_scope_fails_closed_without_a_request() -> None:
    with pytest.raises(ToolError):
        require_scope(_ctx_with(None), scope=SCOPE_ROADMAPS_READ)
