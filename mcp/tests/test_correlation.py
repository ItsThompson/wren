"""MCP CorrelationMiddleware: per-request ``request_id`` binding via contextvars.

Mirrors the backend's ``test_correlation`` shape but asserts the MCP-side policy:
the middleware is mounted app-wide (so non-guarded paths like ``/healthz`` and
``/metrics`` are correlated too, not only the bearer-guarded ``/mcp`` prefix),
and it always MINTS a fresh id (the RS is the
origin of an agent action and never honors an inbound ``X-Request-ID`` from the
internet-facing agent surface).

Being pure-ASGI, the bindings live in the request's own contextvars context, so
they survive to the inner app; a ``BaseHTTPMiddleware`` would run the inner app in
a separate context and lose them. Agent-action correlation end to end (the
``tool_invoked`` line and the forwarded ``X-Request-ID``) is unchanged and stays
covered by ``test_correlation_logging``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

from wren_mcp.correlation import CorrelationMiddleware

if TYPE_CHECKING:
    from starlette.types import Receive, Scope, Send

_MINTED_ID = re.compile(r"[0-9a-f]{32}")


async def _noop_receive() -> dict[str, str]:
    return {}


async def _noop_send(_message: object) -> None:
    return None


async def _seen_by_inner(scope: Scope) -> dict[str, object]:
    """Drive the middleware over one scope; return the contextvars the inner app
    observed (the pure-ASGI guarantee that bindings survive downward)."""
    seen: dict[str, object] = {}

    async def inner(_scope: Scope, _receive: Receive, _send: Send) -> None:
        seen.update(structlog.contextvars.get_contextvars())

    middleware = CorrelationMiddleware(inner, service="wren-mcp")
    await middleware(scope, _noop_receive, _noop_send)
    return seen


def _http_scope(path: str, *, headers: list[tuple[bytes, bytes]] | None = None) -> Scope:
    return {"type": "http", "path": path, "headers": headers or []}


async def test_binds_request_id_and_service_on_a_non_guarded_path() -> None:
    # The interim seam correlated only the guarded /mcp prefix; the app-wide
    # middleware now correlates /healthz too (and /metrics, PRM).
    seen = await _seen_by_inner(_http_scope("/healthz"))
    assert _MINTED_ID.fullmatch(str(seen["request_id"]))
    assert seen["service"] == "wren-mcp"


async def test_a_second_request_gets_a_different_request_id() -> None:
    first = await _seen_by_inner(_http_scope("/metrics"))
    second = await _seen_by_inner(_http_scope("/metrics"))
    assert first["request_id"] != second["request_id"]


async def test_leftover_bindings_are_cleared_before_the_request() -> None:
    # A reused worker context must not leak a prior request's bindings.
    structlog.contextvars.bind_contextvars(user_id="stale-actor")
    seen = await _seen_by_inner(_http_scope("/mcp/"))
    assert "user_id" not in seen
    assert _MINTED_ID.fullmatch(str(seen["request_id"]))


async def test_inbound_request_id_is_not_honored_agent_origin() -> None:
    # The RS is the origin of an agent action: it always mints, never trusts an
    # inbound X-Request-ID from the internet-facing agent surface.
    seen = await _seen_by_inner(
        _http_scope("/mcp/", headers=[(b"x-request-id", b"inbound-attacker-id")])
    )
    assert seen["request_id"] != "inbound-attacker-id"
    assert _MINTED_ID.fullmatch(str(seen["request_id"]))


async def test_non_http_scopes_pass_through_untouched() -> None:
    # Lifespan/websocket scopes reach the inner app unmodified and bind nothing.
    seen = await _seen_by_inner({"type": "lifespan"})
    assert seen == {}
