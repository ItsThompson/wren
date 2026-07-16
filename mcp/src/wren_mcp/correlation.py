"""Per-request correlation via structlog contextvars (MCP side).

A pure-ASGI middleware that, once per HTTP request, clears any contextvars left
over from a reused worker context and binds a freshly minted ``request_id`` (and
the RS ``service`` tag). ``merge_contextvars`` is already first in the structlog
chain (``mcp/logging.py``), so every subsequent line: the tool layer's, the
internal-hop client's: carries the same ``request_id`` with no processor-chain
change. The internal client forwards this id to the backend as ``X-Request-ID``
so one agent action is traceable across the MCP -> backend hop.

Mirrors the backend's :class:`wren.core.correlation.CorrelationMiddleware` in
shape (pure-ASGI, mounted app-wide) with one deliberate difference: the RS is the
**origin** of an agent action, so it always mints a fresh id and never honors an
inbound ``X-Request-ID`` from the internet-facing agent surface. Being app-wide
(not folded into the bearer guard) means the non-guarded paths (``/health``,
``/metrics``, the PRM document) are correlated too.

It must *not* be a ``BaseHTTPMiddleware``: that runs the handler in a separate
``contextvars`` context, so bindings made here would be invisible to the tool
layer. Being pure-ASGI, the bindings live in the request's own context.
"""

from __future__ import annotations

from uuid import uuid4

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send


class CorrelationMiddleware:
    """Bind a per-request ``request_id`` (and the RS ``service``) into contextvars."""

    def __init__(self, app: ASGIApp, *, service: str) -> None:
        self.app = app
        self._service = service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            # Clear first: a worker's context is reused across requests, so a prior
            # request's bindings must not leak into this one.
            structlog.contextvars.clear_contextvars()
            structlog.contextvars.bind_contextvars(request_id=uuid4().hex, service=self._service)
        await self.app(scope, receive, send)
