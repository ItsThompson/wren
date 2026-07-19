"""MCP Resource Server application assembly.

``create_rs_app`` wires the RS: structured logging, the public PRM + health +
``/metrics`` endpoints, the JWKS readiness check, and the bearer-auth boundary
guarding the MCP transport prefix. The token verifier, key provider, and internal
client are injected so tests substitute the network; ``build_app`` composes the
production graph (httpx-backed JWKS discovery + internal client) and manages their
lifecycle.

The MCP tool transport that sits behind the bearer boundary is routed here: the
write tools via:func:`register_write_tools` and the read tools
 via:func:`register_read_tools`, registered alongside onto the same
server.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from starlette.routing import Route
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from wren_mcp.auth import BearerAuthMiddleware
from wren_mcp.client import InternalApiClient, create_internal_http_client
from wren_mcp.config import MCP_PATH, PRM_PATH
from wren_mcp.correlation import CorrelationMiddleware
from wren_mcp.health import create_health_router, jwks_readiness_check
from wren_mcp.keys import JsonFetch, KeyProvider, RemoteKeyProvider
from wren_mcp.logging import configure_logging, get_logger
from wren_mcp.mcp_server import create_mcp_server
from wren_mcp.metrics import instrument
from wren_mcp.prm import build_prm_document
from wren_mcp.settings import RsSettings, build_rs_settings
from wren_mcp.state import RsDeps, set_rs_deps
from wren_mcp.tokens import AgentTokenVerifier
from wren_mcp.tools_read import register_read_tools
from wren_mcp.tools_write import register_write_tools

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.types import Lifespan

# Bound so a hung AS cannot pin the discovery/readiness call indefinitely.
_DISCOVERY_TIMEOUT_SECONDS = 10.0
# Metadata responses must not be cached by intermediaries.
_NO_STORE = {"Cache-Control": "no-store"}


def _compose_lifespan(
    session_manager: StreamableHTTPSessionManager,
    inner: Lifespan[FastAPI] | None,
) -> Lifespan[FastAPI]:
    """Wrap the MCP session manager's lifecycle around any injected lifespan.

    The routed Streamable HTTP transport requires its session manager running
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

    async def protected_resource_metadata() -> JSONResponse:
        return JSONResponse(document, headers=_NO_STORE)

    router.add_api_route(
        PRM_PATH,
        protected_resource_metadata,
        methods=["GET"],
        include_in_schema=False,
    )
    router.add_api_route(
        f"{PRM_PATH}{MCP_PATH}",
        protected_resource_metadata,
        methods=["GET"],
        include_in_schema=False,
    )
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

    # The MCP tool surface: register the write + read tools onto the shared server,
    # then route its Streamable HTTP transport under the bearer-guarded MCP prefix.
    # Calling streamable_http_app() has the side effect of creating the session
    # manager (its property raises otherwise); the returned sub-app is not mounted
    # (a Mount would 307-redirect /mcp -> /mcp/, see the explicit routes below).
    mcp = create_mcp_server(settings)
    register_write_tools(mcp, internal_client)
    register_read_tools(mcp, internal_client)
    mcp.streamable_http_app()
    transport = StreamableHTTPASGIApp(mcp.session_manager)

    app = FastAPI(
        title=f"wren ({settings.service})",
        version="0.1.0",
        lifespan=_compose_lifespan(mcp.session_manager, lifespan),
    )
    app.state.settings = settings
    app.state.log = log
    # The injected seams the RS exposes, behind one typed façade (F11): the JWKS
    # key provider, the bearer verifier, and the internal client the tools call.
    set_rs_deps(
        app,
        RsDeps(
            key_provider=key_provider,
            token_verifier=verifier,
            internal_client=internal_client,
        ),
    )

    app.include_router(_create_prm_router(settings))
    app.include_router(create_health_router([jwks_readiness_check(key_provider)]))
    # Serve POST /mcp (no slash) directly, matching /mcp/. Two explicit full-match
    # routes bound to the bare ASGI transport: an outer Mount only PARTIAL-matches
    # /mcp, so redirect_slashes emits a 307 -> /mcp/ that stalls https->http MCP
    # clients (~30s). StreamableHTTPASGIApp ignores the leftover path, so both
    # routes delegate identically to the session manager. Route objects are
    # appended directly (not app.add_route, which mypy --strict rejects: the ASGI3
    # callable does not match its Request-endpoint signature).
    app.router.routes.append(Route(MCP_PATH, transport))
    app.router.routes.append(Route(f"{MCP_PATH}/", transport))

    # The agent trust boundary: guard the MCP transport prefix. Added before
    # instrument() so the metrics middleware wraps it and counts the boundary's
    # 401s too.
    app.add_middleware(
        BearerAuthMiddleware,
        verifier=verifier,
        resource=settings.resource,
        protected_prefix=MCP_PATH,
    )
    instrument(app)

    # Correlation is mounted here so it is outermost among the always-on
    # middleware: request_id is bound before the metrics middleware, the bearer
    # guard, and the tool layer run, so the non-guarded paths (/health, /metrics,
    # PRM) are correlated too. In production ProxyHeadersMiddleware is added after
    # this and becomes the true outermost layer, rewriting the scheme before
    # correlation runs.
    app.add_middleware(CorrelationMiddleware, service=settings.service)
    if settings.allowed_cors_origins:
        # Dev-only (see ``RsSettings.allowed_cors_origins``): the browser MCP
        # Inspector runs OAuth discovery and token-exchange fetches from its own
        # origin, so it needs CORS. Mounted outermost so a preflight to the
        # bearer-guarded /mcp transport clears CORS before the guard 401s it.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    if settings.trusted_proxies:
        # Behind the Cloudflare tunnel uvicorn receives plaintext http and does not
        # trust the tunnel's X-Forwarded-Proto, so any request-derived absolute URL
        # is emitted as http. Trust the pinned app-net CIDR only (never ``*``):
        # rewrite scope scheme/client from X-Forwarded-* solely when the connecting
        # IP is in that CIDR; from any other IP it is a pass-through. Added last so
        # it is the outermost middleware and rewrites the scheme before correlation
        # or the bearer guard read the request. Empty in dev -> not mounted.
        app.add_middleware(
            ProxyHeadersMiddleware,
            trusted_hosts=settings.trusted_proxies,
        )

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
        # Two independent clients (JWKS discovery + internal API); close them
        # concurrently on shutdown.
        await asyncio.gather(discovery_client.aclose(), internal_http.aclose())

    return create_rs_app(
        settings,
        key_provider=key_provider,
        internal_client=internal_client,
        lifespan=lifespan,
    )
