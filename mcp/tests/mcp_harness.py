"""Test harness: drive the mounted MCP write tools over the real transport.

Builds the actual Resource-Server app (:func:`create_rs_app`) with a faked JWKS
provider and a ``MockTransport``-backed internal client, then issues MCP
``tools/call`` / ``tools/list`` requests over the mounted Streamable HTTP
transport with a real minted bearer. This exercises the whole path the way an
agent hits it (bearer boundary -> identity on request.state -> tool dispatch ->
one internal HTTP call -> structured output), mocking only the true external
boundary: the backend internal API.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from token_factory import ISSUER, RESOURCE, make_fetch, mint, new_key, public_jwks
from wren_mcp.app import create_rs_app
from wren_mcp.client import InternalApiClient
from wren_mcp.keys import RemoteKeyProvider
from wren_mcp.settings import SERVICE, RsSettings

BackendHandler = Callable[[httpx.Request], httpx.Response]
_INTERNAL_BASE = "http://backend:8001"
_API_TOKEN = "shared-internal-token"
_MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _settings() -> RsSettings:
    return RsSettings(
        service=SERVICE,
        environment="production",
        log_level="critical",
        host="127.0.0.1",
        port=9000,
        issuer=ISSUER,
        resource=RESOURCE,
        backend_internal_url=_INTERNAL_BASE,
        internal_api_token=_API_TOKEN,
    )


class AgentHarness:
    """A TestClient over the mounted MCP transport plus captured backend calls."""

    def __init__(
        self, backend: BackendHandler, *, sub: str = "user-ada", scope: str | None = None
    ) -> None:
        self.captured: list[httpx.Request] = []

        def capture(request: httpx.Request) -> httpx.Response:
            self.captured.append(request)
            return backend(request)

        key = new_key()
        provider = RemoteKeyProvider(ISSUER, make_fetch(public_jwks(key)))
        http = httpx.AsyncClient(base_url=_INTERNAL_BASE, transport=httpx.MockTransport(capture))
        self._client = InternalApiClient(http, api_token=_API_TOKEN)
        self.app: FastAPI = create_rs_app(
            _settings(), key_provider=provider, internal_client=self._client
        )
        # A per-test scope override lets the scope-gate tests mint a token that is
        # missing a required scope; the default mirrors token_factory.mint's default
        # (roadmaps:read + roadmaps:write) so existing tool tests are unaffected.
        token = mint(key, sub=sub) if scope is None else mint(key, sub=sub, scope=scope)
        self._auth = {"Authorization": f"Bearer {token}"}

    def _rpc(self, client: TestClient, method: str, params: dict[str, Any]) -> dict[str, Any]:
        response = client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            headers={**_MCP_HEADERS, **self._auth},
        )
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def call_tool(self, client: TestClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool; return its ``CallToolResult`` (``isError`` + content)."""
        body = self._rpc(client, "tools/call", {"name": name, "arguments": arguments})
        result: dict[str, Any] = body["result"]
        return result

    def list_tools(self, client: TestClient) -> list[dict[str, Any]]:
        body = self._rpc(client, "tools/list", {})
        tools: list[dict[str, Any]] = body["result"]["tools"]
        return tools

    def open(self) -> TestClient:
        return TestClient(self.app, base_url=RESOURCE)


def json_error(status: int, code: str, detail: str, **extra: Any) -> httpx.Response:
    """A backend RFC 9457 problem+json error response for the harness."""
    body = {
        "type": f"https://usewren.com/errors/{code.lower()}",
        "title": code,
        "status": status,
        "code": code,
        "detail": detail,
        **extra,
    }
    return httpx.Response(status, json=body, headers={"content-type": "application/problem+json"})
