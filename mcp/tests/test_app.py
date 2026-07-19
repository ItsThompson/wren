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
from fastapi import Request  # noqa: TC002 - FastAPI reads this route param annotation at runtime
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


_TOOLS_LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
_MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}
# Registered tool surface: seven write tools + seven read tools.
_TOOL_COUNT = 14


def _authed_client(make_settings: MakeSettings) -> tuple[TestClient, dict[str, str]]:
    """An RS app plus a valid bearer for the registered tool surface.

    Boots one app instance (one session manager, ``run()`` once per instance), so
    a caller probes both ``/mcp`` and ``/mcp/`` within a single TestClient
    context."""
    key = new_key()
    app = create_rs_app(
        make_settings(),
        key_provider=RemoteKeyProvider(ISSUER, make_fetch(public_jwks(key))),
        internal_client=_internal_client(),
    )
    headers = {"Authorization": f"Bearer {mint(key)}", **_MCP_HEADERS}
    return TestClient(app, base_url=RESOURCE), headers


def _tool_names(response: httpx.Response) -> set[str]:
    return {tool["name"] for tool in response.json()["result"]["tools"]}


# The pinned edge-net CIDR the trusted-proxy tests exercise (see docker-compose).
_TRUSTED_CIDR = "10.89.0.0/24"
_TRUSTED_IP = ("10.89.0.5", 12345)
_UNTRUSTED_IP = ("10.9.9.9", 12345)


def _scheme_probe_client(
    make_settings: MakeSettings,
    *,
    trusted_proxies: list[str],
    client: tuple[str, int],
) -> TestClient:
    """An RS app with a GET /scheme route echoing ``request.url.scheme``.

    ``client`` sets the connecting IP the ProxyHeadersMiddleware trust-checks;
    TestClient's default (``("testclient", 50000)``) is a non-IP literal that no
    CIDR matches, so the trust cases MUST override it with an in/out-of-CIDR IP.
    """
    app = create_rs_app(
        make_settings(trusted_proxies=trusted_proxies),
        key_provider=RemoteKeyProvider(ISSUER, make_fetch(public_jwks(new_key()))),
        internal_client=_internal_client(),
    )

    @app.get("/scheme")
    async def scheme(request: Request) -> dict[str, str]:
        return {"scheme": request.url.scheme}

    return TestClient(app, client=client)


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
    # A valid token clears the auth boundary and reaches the now-routed MCP tool
    # transport; tools/list returns the registered write tools.
    client, headers = _authed_client(make_settings)
    with client:
        response = client.post(f"{MCP_PATH}/", json=_TOOLS_LIST, headers=headers)

    assert response.status_code == 200
    assert "create_roadmap_draft" in _tool_names(response)


def test_authenticated_post_mcp_no_slash_is_served_directly(make_settings: MakeSettings) -> None:
    # AC1 (decisive): the authenticated POST /mcp (no slash) is served directly
    # (200, no Location, no 307), identical to POST /mcp/. The old outer Mount
    # 307-redirected /mcp -> /mcp/, stalling https->http MCP clients (~30s). An
    # UNAUTH probe cannot catch this: BearerAuth 401s /mcp before routing, so the
    # redirect only ever fired on the authenticated path.
    client, headers = _authed_client(make_settings)
    with client:
        no_slash = client.post(MCP_PATH, json=_TOOLS_LIST, headers=headers, follow_redirects=False)
        with_slash = client.post(
            f"{MCP_PATH}/", json=_TOOLS_LIST, headers=headers, follow_redirects=False
        )

    assert no_slash.status_code == 200
    assert "Location" not in no_slash.headers
    assert with_slash.status_code == 200
    # Parity: the no-slash path resolves the identical tool surface as /mcp/.
    assert _tool_names(no_slash) == _tool_names(with_slash)
    assert "create_roadmap_draft" in _tool_names(no_slash)


def test_all_tools_are_callable_over_both_mcp_paths(make_settings: MakeSettings) -> None:
    # AC4: the full 14-tool surface is reachable over both /mcp and /mcp/.
    client, headers = _authed_client(make_settings)
    with client:
        no_slash = client.post(MCP_PATH, json=_TOOLS_LIST, headers=headers)
        with_slash = client.post(f"{MCP_PATH}/", json=_TOOLS_LIST, headers=headers)

    assert len(_tool_names(no_slash)) == _TOOL_COUNT
    assert len(_tool_names(with_slash)) == _TOOL_COUNT


def test_unauthenticated_post_mcp_is_401_with_no_location(make_settings: MakeSettings) -> None:
    # AC2: both /mcp and /mcp/ reject an unauthenticated POST at the boundary with
    # the PRM-pointing challenge and never emit a Location.
    client = _build(make_settings)
    for path in (MCP_PATH, f"{MCP_PATH}/"):
        response = client.post(path, follow_redirects=False)
        assert response.status_code == 401
        challenge = response.headers["WWW-Authenticate"]
        assert challenge == f'Bearer resource_metadata="{RESOURCE}{PRM_PATH}"'
        assert "Location" not in response.headers


def test_trusted_proxy_forwarded_scheme_is_honored(make_settings: MakeSettings) -> None:
    # AC5: from an IP inside the pinned edge-net CIDR, X-Forwarded-Proto: https is
    # trusted, so the app sees request.url.scheme == "https".
    client = _scheme_probe_client(
        make_settings, trusted_proxies=[_TRUSTED_CIDR], client=_TRUSTED_IP
    )
    response = client.get("/scheme", headers={"X-Forwarded-Proto": "https"})
    assert response.json()["scheme"] == "https"


def test_untrusted_proxy_forwarded_scheme_is_ignored(make_settings: MakeSettings) -> None:
    # AC5: from an IP outside the CIDR the forwarded header is ignored; the scheme
    # stays http even though the same header is sent.
    client = _scheme_probe_client(
        make_settings, trusted_proxies=[_TRUSTED_CIDR], client=_UNTRUSTED_IP
    )
    response = client.get("/scheme", headers={"X-Forwarded-Proto": "https"})
    assert response.json()["scheme"] == "http"


def test_empty_trusted_proxies_leaves_the_scheme_untouched(make_settings: MakeSettings) -> None:
    # Dev: with trusted_proxies empty the middleware is not mounted, so even from
    # an in-CIDR IP the forwarded scheme is never honored.
    client = _scheme_probe_client(make_settings, trusted_proxies=[], client=_TRUSTED_IP)
    response = client.get("/scheme", headers={"X-Forwarded-Proto": "https"})
    assert response.json()["scheme"] == "http"


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
