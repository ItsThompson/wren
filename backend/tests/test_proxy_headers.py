"""Proxy-header trust: the external app honors X-Forwarded-Proto from a trusted
edge-net IP; the internal app never does.

Behind the Cloudflare tunnel uvicorn receives plaintext http, so the external
app mounts uvicorn's ``ProxyHeadersMiddleware`` (gated on ``trusted_proxies``) to
adopt the tunnel's ``X-Forwarded-Proto`` when the connecting IP is in the pinned
edge-net CIDR. The behavior is asserted on an external-shaped app (mirroring the
external entrypoint's proxy wiring, as ``test_identity`` mirrors its identity
wiring) and on the internal-shaped app, which never mounts it. The security-
critical invariant (the real internal app trusts no proxy headers) is also
asserted structurally against the real app.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import Request  # noqa: TC002 - FastAPI reads this route param annotation at runtime
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from wren.api_internal.main import app as real_internal_app
from wren.core.app_factory import create_app
from wren.core.settings import AppSettings

if TYPE_CHECKING:
    import pytest
    from fastapi import FastAPI

MakeSettings = Callable[..., AppSettings]


def _middleware_class_names(app: FastAPI) -> set[str]:
    # Starlette types Middleware.cls as a factory protocol, so identity/`in`
    # checks against the concrete class trip mypy; compare by class name instead.
    return {getattr(mw.cls, "__name__", "") for mw in app.user_middleware}


# The pinned edge-net CIDR (see docker-compose) and IPs in/outside it.
_TRUSTED_CIDR = "10.89.0.0/24"
_TRUSTED_IP = ("10.89.0.5", 12345)
_UNTRUSTED_IP = ("10.9.9.9", 12345)


def _external_scheme_client(
    make_settings: MakeSettings,
    *,
    trusted_proxies: list[str],
    client: tuple[str, int],
) -> TestClient:
    """An external-shaped app with a GET /scheme route, mirroring the external
    entrypoint's ProxyHeadersMiddleware wiring (mounted outermost when
    ``trusted_proxies`` is set). ``client`` sets the connecting IP the middleware
    trust-checks; TestClient's default is a non-IP literal no CIDR matches."""
    settings = make_settings(trusted_proxies=trusted_proxies)
    app = create_app(settings)

    @app.get("/scheme")
    async def scheme(request: Request) -> dict[str, str]:
        return {"scheme": request.url.scheme}

    if settings.trusted_proxies:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxies)
    return TestClient(app, client=client)


def _internal_scheme_client(
    make_settings: MakeSettings,
    *,
    trusted_proxies: list[str],
    client: tuple[str, int],
) -> TestClient:
    """An internal-shaped app with a GET /scheme route. Mirrors the internal
    entrypoint, which never mounts ProxyHeadersMiddleware regardless of the
    trusted-proxy setting it inherits from the shared env."""
    settings = make_settings(trusted_proxies=trusted_proxies)
    app = create_app(settings)

    @app.get("/scheme")
    async def scheme(request: Request) -> dict[str, str]:
        return {"scheme": request.url.scheme}

    return TestClient(app, client=client)


def test_external_honors_forwarded_scheme_from_a_trusted_proxy(
    make_settings: MakeSettings,
) -> None:
    client = _external_scheme_client(
        make_settings, trusted_proxies=[_TRUSTED_CIDR], client=_TRUSTED_IP
    )
    response = client.get("/scheme", headers={"X-Forwarded-Proto": "https"})
    assert response.json()["scheme"] == "https"


def test_external_ignores_forwarded_scheme_from_an_untrusted_proxy(
    make_settings: MakeSettings,
) -> None:
    client = _external_scheme_client(
        make_settings, trusted_proxies=[_TRUSTED_CIDR], client=_UNTRUSTED_IP
    )
    response = client.get("/scheme", headers={"X-Forwarded-Proto": "https"})
    assert response.json()["scheme"] == "http"


def test_external_without_trusted_proxies_leaves_scheme_untouched(
    make_settings: MakeSettings,
) -> None:
    # Dev: empty trusted_proxies means the middleware is not mounted, so even an
    # in-CIDR IP's forwarded scheme is ignored.
    client = _external_scheme_client(make_settings, trusted_proxies=[], client=_TRUSTED_IP)
    response = client.get("/scheme", headers={"X-Forwarded-Proto": "https"})
    assert response.json()["scheme"] == "http"


def test_internal_never_honors_forwarded_scheme(make_settings: MakeSettings) -> None:
    # Even with a CIDR configured and an in-CIDR connecting IP, the internal app
    # mounts no proxy middleware, so the forwarded scheme is never adopted.
    client = _internal_scheme_client(
        make_settings, trusted_proxies=[_TRUSTED_CIDR], client=_TRUSTED_IP
    )
    response = client.get("/scheme", headers={"X-Forwarded-Proto": "https"})
    assert response.json()["scheme"] == "http"


def test_real_internal_app_mounts_no_proxy_headers_middleware() -> None:
    # Security invariant: the internal app must never trust proxy headers (that
    # would let its caller spoof the client IP), so ProxyHeadersMiddleware must be
    # absent from the real internal app's stack regardless of configuration.
    assert "ProxyHeadersMiddleware" not in _middleware_class_names(real_internal_app)


def test_real_external_app_mounts_proxy_headers_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real external entrypoint mounts ProxyHeadersMiddleware when
    # TRUSTED_PROXIES is configured. Reload the module singleton with the env set,
    # assert the middleware is wired, then reload it back to the unconfigured state
    # so the rest of the suite sees the default app.
    import wren.api.main as external_main

    monkeypatch.setenv("TRUSTED_PROXIES", _TRUSTED_CIDR)
    importlib.reload(external_main)
    try:
        assert "ProxyHeadersMiddleware" in _middleware_class_names(external_main.app)
    finally:
        monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
        importlib.reload(external_main)
