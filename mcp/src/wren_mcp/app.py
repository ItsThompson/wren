"""MCP Resource Server application assembly (spec sections 03/07/08).

``create_rs_app`` wires the RS: structured logging, the public PRM + health +
``/metrics`` endpoints, the JWKS readiness check, and the bearer-auth boundary
guarding the MCP transport prefix. The token verifier, key provider, and internal
client are injected so tests substitute the network; ``build_app`` composes the
production graph (httpx-backed JWKS discovery + internal client) and manages their
lifecycle.

The MCP tool transport that sits behind the bearer boundary is mounted here: the
write tools (Ticket 21) via :func:`register_write_tools`, with the read tools
(Ticket 22) registered alongside onto the same server.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.types import Lifespan

from wren_mcp.auth import BearerAuthMiddleware
from wren_mcp.client import InternalApiClient, create_internal_http_client
from wren_mcp.config import MCP_PATH, PRM_PATH
from wren_mcp.health import create_health_router, jwks_readiness_check
from wren_mcp.keys import JsonFetch, KeyProvider, RemoteKeyProvider
from wren_mcp.logging import configure_logging, get_logger
from wren_mcp.mcp_server import create_mcp_server
from wren_mcp.metrics import instrument
from wren_mcp.prm import build_prm_document
from wren_mcp.settings import RsSettings, build_rs_settings
from wren_mcp.tokens import AgentTokenVerifier
from wren_mcp.tools_write import register_write_tools

# Bound so a hung AS cannot pin the discovery/readiness call indefinitely.
_DISCOVERY_TIMEOUT_SECONDS = 10.0
# Metadata responses must not be cached by intermediaries.
_NO_STORE = {"Cache-Control": "no-store"}


def _compose_lifespan(
    session_manager: StreamableHTTPSessionManager,
    inner: Lifespan[FastAPI] | None,
) -> Lifespan[FastAPI]:
    """Wrap the MCP session manager's lifecycle around any injected lifespan.

    The mounted Streamable HTTP transport requires its session manager running
    for the lifetime of the app; ``build_app`` additionally injects a lifespan
    that closes the httpx clients on shutdown."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with session_manager.run():
            if inner is None:
                yield
            else:
                async with inner(app):
                    yield

    return lifespan


def _create_prm_router(settings: RsSettings) -> APIRouter:
    """The public PRM endpoint (RFC 9728). Built from pinned config, not the host."""
    router = APIRouter(tags=["oauth"])
    document = build_prm_document(resource=settings.resource, issuer=settings.issuer)

    @router.get(PRM_PATH, include_in_schema=False)
    async def protected_resource_metadata() -> JSONResponse:
        return JSONResponse(document, headers=_NO_STORE)

    return router


def create_rs_app(
    settings: RsSettings,
    *,
    key_provider: KeyProvider,
    internal_client: InternalApiClient,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    """Assemble the Resource-Server app from injected dependencies."""
    configure_logging(environment=settings.environment, log_level=settings.log_level)
    log = get_logger(settings.service)

    verifier = AgentTokenVerifier(key_provider, issuer=settings.issuer, resource=settings.resource)

    # The MCP tool surface: register the write tools (Ticket 22 adds the read
    # tools alongside) onto the shared server, then mount its Streamable HTTP
    # transport under the bearer-guarded MCP prefix. Building the ASGI app up
    # front lets the app lifespan drive the session manager it requires.
    mcp = create_mcp_server(settings)
    register_write_tools(mcp, internal_client)
    mcp_transport = mcp.streamable_http_app()

    app = FastAPI(
        title=f"wren ({settings.service})",
        version="0.1.0",
        lifespan=_compose_lifespan(mcp.session_manager, lifespan),
    )
    app.state.settings = settings
    app.state.log = log
    # Seams the MCP tool layer consumes: the write tools read the resolved
    # identity off request.state (set by the boundary middleware) and call the
    # backend internal app through this injected client.
    app.state.key_provider = key_provider
    app.state.token_verifier = verifier
    app.state.internal_client = internal_client

    app.include_router(_create_prm_router(settings))
    app.include_router(create_health_router([jwks_readiness_check(key_provider)]))
    app.mount(MCP_PATH, mcp_transport)

    # The agent trust boundary: guard the MCP transport prefix. Added before
    # instrument() so the metrics middleware stays outermost and counts the
    # boundary's 401s too.
    app.add_middleware(
        BearerAuthMiddleware,
        verifier=verifier,
        resource=settings.resource,
        protected_prefix=MCP_PATH,
    )
    instrument(app)

    log.info(
        "mcp_configured",
        environment=settings.environment,
        port=settings.port,
        issuer=settings.issuer,
        resource=settings.resource,
    )
    return app


def create_json_fetch(client: httpx.AsyncClient) -> JsonFetch:
    """Adapt an ``httpx.AsyncClient`` to the key provider's ``JsonFetch`` seam,
    keeping :mod:`wren_mcp.keys` free of any HTTP-library dependency."""

    async def fetch(url: str) -> dict[str, Any]:
        response = await client.get(url)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    return fetch


def build_app(settings: RsSettings | None = None) -> FastAPI:
    """Compose the production RS: httpx-backed JWKS discovery + internal client,
    with both clients closed on shutdown."""
    settings = settings or build_rs_settings()

    discovery_client = httpx.AsyncClient(timeout=_DISCOVERY_TIMEOUT_SECONDS)
    key_provider = RemoteKeyProvider(settings.issuer, create_json_fetch(discovery_client))
    internal_http = create_internal_http_client(settings)
    internal_client = InternalApiClient(internal_http, api_token=settings.internal_api_token)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await discovery_client.aclose()
        await internal_http.aclose()

    return create_rs_app(
        settings,
        key_provider=key_provider,
        internal_client=internal_client,
        lifespan=lifespan,
    )
