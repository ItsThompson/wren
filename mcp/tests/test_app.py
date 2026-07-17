"""App-assembly tests: PRM, health/readiness, metrics, and the 401 boundary.

Boots the real RS app (:func:`create_rs_app`) with an injected key provider
(faked JWKS) and internal client, and asserts the acceptance-criteria surface end
to end: PRM served from pinned config, /readyz gated on JWKS reachability,
/metrics exposed, and an unauthenticated tool call rejected with 401 +
WWW-Authenticate pointing at the PRM.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from token_factory import ISSUER, RESOURCE, make_fetch, mint, new_key, public_jwks
from wren_mcp.app import build_app, create_json_fetch, create_rs_app
from wren_mcp.client import InternalApiClient
from wren_mcp.config import MCP_PATH, PRM_PATH
from wren_mcp.keys import RemoteKeyProvider
from wren_mcp.settings import RsSettings
from wren_mcp.state import get_rs_deps

if TYPE_CHECKING:
    from joserfc.jwk import KeySet, RSAKey

    from wren_mcp.keys import KeyProvider

MakeSettings = Callable[..., RsSettings]


class _FailingKeyProvider:
    """A key provider whose discovery always fails (AS unreachable)."""

    async def key_set_for(self, kid: str | None) -> KeySet:
        raise RuntimeError("AS unreachable")

    async def load(self) -> KeySet:
        raise RuntimeError("AS unreachable")


def _internal_client() -> InternalApiClient:
    http = httpx.AsyncClient(
        base_url="http://backend:8001",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
    )
    return InternalApiClient(http, api_token=SecretStr("tok"))


def _build(
    make_settings: MakeSettings,
    *,
    key: RSAKey | None = None,
    key_provider: KeyProvider | None = None,
) -> TestClient:
    provider = key_provider or RemoteKeyProvider(ISSUER, make_fetch(public_jwks(key or new_key())))
    app = create_rs_app(make_settings(), key_provider=provider, internal_client=_internal_client())
    return TestClient(app)


def test_prm_is_served_from_pinned_config(make_settings: MakeSettings) -> None:
    client = _build(make_settings)

    response = client.get(PRM_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["resource"] == RESOURCE
    assert body["authorization_servers"] == [ISSUER]


def test_prm_is_served_from_transport_scoped_discovery_path(
    make_settings: MakeSettings,
) -> None:
    client = _build(make_settings)

    response = client.get(f"{PRM_PATH}{MCP_PATH}")

    assert response.status_code == 200
    assert response.json()["resource"] == RESOURCE


def test_prm_urls_ignore_the_request_host(make_settings: MakeSettings) -> None:
    # The Site-URL gotcha: even if a client reaches the origin under a different
    # Host, the PRM advertises the pinned resource/issuer.
    client = _build(make_settings)

    response = client.get(PRM_PATH, headers={"Host": "backend:9000"})

    assert response.json()["resource"] == RESOURCE


def test_healthz_is_ok(make_settings: MakeSettings) -> None:
    client = _build(make_settings)
    assert client.get("/healthz").status_code == 200


def test_readyz_is_ready_when_jwks_loads(make_settings: MakeSettings) -> None:
    client = _build(make_settings)

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["checks"]["as_jwks"]["ok"] is True


def test_readyz_is_503_when_jwks_is_unreachable(make_settings: MakeSettings) -> None:
    client = _build(make_settings, key_provider=_FailingKeyProvider())

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["checks"]["as_jwks"]["ok"] is False


def test_metrics_are_exposed(make_settings: MakeSettings) -> None:
    client = _build(make_settings)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "http_requests_total" in response.text
    assert "http_request_duration_seconds" in response.text
    # The shared MCP domain registry is served alongside the private HTTP one.
    assert "mcp_tool_invocations_total" in response.text


def test_unauthenticated_tool_call_is_401_pointing_at_the_prm(make_settings: MakeSettings) -> None:
    client = _build(make_settings)

    response = client.get(MCP_PATH)

    assert response.status_code == 401
    challenge = response.headers["WWW-Authenticate"]
    assert challenge == f'Bearer resource_metadata="{RESOURCE}{PRM_PATH}"'


def test_development_cors_allows_mcp_inspector_discovery_preflight(
    make_settings: MakeSettings,
) -> None:
    client = _build(lambda **overrides: make_settings(environment="development", **overrides))

    response = client.options(
        f"{PRM_PATH}{MCP_PATH}",
        headers={
            "origin": "http://localhost:6274",
            "access-control-request-method": "GET",
            "access-control-request-headers": "mcp-protocol-version",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:6274"


def test_development_cors_allows_mcp_transport_preflight(
    make_settings: MakeSettings,
) -> None:
    # The /mcp transport is bearer-guarded, so its preflight is the one that must
    # clear CORS *before* the guard 401s the OPTIONS. CORS is mounted outermost in
    # dev, so the preflight is answered without reaching the guard.
    client = _build(lambda **overrides: make_settings(environment="development", **overrides))

    response = client.options(
        MCP_PATH,
        headers={
            "origin": "http://localhost:6274",
            "access-control-request-method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:6274"


def test_production_does_not_allow_the_mcp_inspector_origin(
    make_settings: MakeSettings,
) -> None:
    # The Inspector widening is gated on is_dev: production mounts no CORS, so the
    # preflight from :6274 is never echoed back and the origin stays locked out.
    client = _build(make_settings)

    response = client.options(
        MCP_PATH,
        headers={
            "origin": "http://localhost:6274",
            "access-control-request-method": "POST",
        },
    )

    assert response.headers.get("access-control-allow-origin") != "http://localhost:6274"


def test_valid_bearer_passes_the_boundary(make_settings: MakeSettings) -> None:
    # A valid token clears the auth boundary and reaches the now-mounted MCP tool
    # transport; tools/list returns the registered write tools.
    key = new_key()
    app = create_rs_app(
        make_settings(),
        key_provider=RemoteKeyProvider(ISSUER, make_fetch(public_jwks(key))),
        internal_client=_internal_client(),
    )
    with TestClient(app, base_url=RESOURCE) as client:
        response = client.post(
            f"{MCP_PATH}/",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={
                "Authorization": f"Bearer {mint(key)}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )

    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert "create_roadmap_draft" in names


def test_app_exposes_the_tool_layer_seams(make_settings: MakeSettings) -> None:
    provider = RemoteKeyProvider(ISSUER, make_fetch(public_jwks(new_key())))
    internal_client = _internal_client()
    app = create_rs_app(make_settings(), key_provider=provider, internal_client=internal_client)

    # The seams the tool dispatch builds on, behind the typed RsDeps façade: the
    # verified-identity verifier and the internal client the tools call.
    deps = get_rs_deps(app)
    assert deps.internal_client is internal_client
    assert deps.token_verifier is not None
    assert deps.key_provider is provider


async def test_create_json_fetch_parses_json() -> None:
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={"jwks_uri": "u"}))
    )
    fetch = create_json_fetch(http)

    assert await fetch("https://api.usewren.com/.well-known/oauth-authorization-server") == {
        "jwks_uri": "u"
    }
    await http.aclose()


async def test_create_json_fetch_raises_on_error_status() -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(503)))
    fetch = create_json_fetch(http)

    with pytest.raises(httpx.HTTPStatusError):
        await fetch("https://api.usewren.com/jwks")
    await http.aclose()


def test_build_app_boots_and_cleans_up_its_clients(make_settings: MakeSettings) -> None:
    # Exercises the production wiring graph (httpx-backed discovery + internal
    # client) and the lifespan that closes both clients on shutdown. The context
    # manager runs startup + shutdown; JWKS is lazy, so no network is hit.
    app = build_app(make_settings())
    with TestClient(app) as client:
        assert client.get(PRM_PATH).status_code == 200


def test_main_module_builds_the_app() -> None:
    import wren_mcp.main as main_module

    with TestClient(main_module.app) as client:
        assert client.get(PRM_PATH).status_code == 200
