"""CorrelationMiddleware: per-request request_id binding via structlog contextvars.

Exercised through the real middleware wired by ``create_app`` and asserted with
structlog's ``capture_logs`` running the real ``merge_contextvars`` processor
(never a mock). Being pure-ASGI, the bindings live in the request's own context,
so they survive into the handler and out to the catch-all 500 log; a
``BaseHTTPMiddleware`` would run the handler in a separate context and lose them.

``get_logger`` binds eagerly at import (freezing the pre-``configure_logging``
processor list), so module-level loggers are not visible to ``capture_logs``.
Tests therefore emit via a fresh ``structlog.get_logger()`` inside the capture
block, which ``capture_logs`` does intercept.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import pytest
import structlog
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from wren.core.app_factory import create_app
from wren.core.correlation import REQUEST_ID_HEADER, CorrelationMiddleware
from wren.core.errors import build_exception_handlers
from wren.core.identity import StripInboundIdentityMiddleware
from wren.core.settings import AppSettings

if TYPE_CHECKING:
    from collections.abc import MutableMapping

MakeSettings = Callable[..., AppSettings]

_MINTED_ID = re.compile(r"[0-9a-f]{32}")


@pytest.fixture(autouse=True)
def _isolate_contextvars() -> None:
    # Unit tests that drive the middleware directly run in the test thread; clear
    # so a prior test's bindings never leak into a later assertion.
    structlog.contextvars.clear_contextvars()


def _app(make_settings: MakeSettings, *, service: str = "wren-test") -> FastAPI:
    router = APIRouter()

    @router.get("/emit-two")
    async def emit_two() -> dict[str, str]:
        # Fresh loggers so capture_logs intercepts them; merge_contextvars then
        # attaches the request_id the middleware bound.
        structlog.get_logger().info("first_line")
        structlog.get_logger().info("second_line")
        # Return what the handler sees so a test can confirm the middleware's
        # bindings survived to the handler (the pure-ASGI guarantee).
        seen = structlog.contextvars.get_contextvars()
        return {"request_id": seen.get("request_id", ""), "service": seen.get("service", "")}

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    return create_app(
        make_settings(service=service),
        routers=[router],
        exception_handlers=build_exception_handlers(),
    )


def _entries(logs: list[MutableMapping[str, Any]], event: str) -> list[MutableMapping[str, Any]]:
    return [entry for entry in logs if entry.get("event") == event]


def _one(logs: list[MutableMapping[str, Any]], event: str) -> MutableMapping[str, Any]:
    matches = _entries(logs, event)
    assert len(matches) == 1
    return matches[0]


def test_two_lines_in_one_request_share_the_request_id(make_settings: MakeSettings) -> None:
    client = TestClient(_app(make_settings))
    with capture_logs(processors=[merge_contextvars]) as logs:
        body = client.get("/emit-two").json()

    first = _one(logs, "first_line")
    second = _one(logs, "second_line")
    assert first["request_id"]
    assert first["request_id"] == second["request_id"]
    # The id the handler saw is the same id bound onto both log lines: the
    # binding survived to the handler, which BaseHTTPMiddleware would break.
    assert body["request_id"] == first["request_id"]


def test_a_second_request_gets_a_different_request_id(make_settings: MakeSettings) -> None:
    client = TestClient(_app(make_settings))
    first = client.get("/emit-two").json()["request_id"]
    second = client.get("/emit-two").json()["request_id"]
    assert first and second
    assert first != second


def test_inbound_request_id_is_honored(make_settings: MakeSettings) -> None:
    client = TestClient(_app(make_settings))
    with capture_logs(processors=[merge_contextvars]) as logs:
        body = client.get("/emit-two", headers={REQUEST_ID_HEADER: "inbound-abc-123"}).json()

    assert body["request_id"] == "inbound-abc-123"
    assert _one(logs, "first_line")["request_id"] == "inbound-abc-123"


def test_request_id_is_minted_when_absent(make_settings: MakeSettings) -> None:
    body = TestClient(_app(make_settings)).get("/emit-two").json()
    assert _MINTED_ID.fullmatch(body["request_id"])


@pytest.mark.parametrize(
    "bad_inbound",
    [
        pytest.param("has spaces and !@#", id="illegal-charset"),
        pytest.param("x" * 129, id="over-length"),
    ],
)
def test_malformed_inbound_request_id_is_replaced_with_a_minted_one(
    make_settings: MakeSettings, bad_inbound: str
) -> None:
    body = (
        TestClient(_app(make_settings))
        .get("/emit-two", headers={REQUEST_ID_HEADER: bad_inbound})
        .json()
    )
    # A malformed inbound id never reaches a log field; a fresh id is minted.
    assert body["request_id"] != bad_inbound
    assert _MINTED_ID.fullmatch(body["request_id"])


def test_service_is_bound_per_app(make_settings: MakeSettings) -> None:
    external = TestClient(_app(make_settings, service="wren-external")).get("/emit-two").json()
    internal = TestClient(_app(make_settings, service="wren-internal")).get("/emit-two").json()
    assert external["service"] == "wren-external"
    assert internal["service"] == "wren-internal"


def test_catch_all_500_log_carries_the_request_id(
    make_settings: MakeSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_app(make_settings), raise_server_exceptions=False)
    with capture_logs(processors=[merge_contextvars]) as logs:
        # Reset the frozen module logger to a fresh proxy so capture_logs (with
        # merge_contextvars) intercepts the fault log and shows request_id.
        monkeypatch.setattr("wren.core.errors._log", structlog.get_logger())
        response = client.get("/boom", headers={REQUEST_ID_HEADER: "boom-corr-1"})

    assert response.status_code == 500
    fault = _one(logs, "unhandled_exception")
    # the fault log is correlated to the faulting request.
    assert fault["request_id"] == "boom-corr-1"
    assert fault["path"] == "/boom"


def test_500_log_keeps_request_id_when_correlation_is_not_outermost(
    make_settings: MakeSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mirror the external app: StripInbound (and, in prod, CORS) sit OUTSIDE
    # CorrelationMiddleware. request_id must still reach the fault log, which
    # runs in the outermost ServerErrorMiddleware, because a pure-ASGI middleware's
    # contextvar bindings persist up the call stack (BaseHTTPMiddleware would not).
    app = _app(make_settings)
    app.add_middleware(StripInboundIdentityMiddleware)
    client = TestClient(app, raise_server_exceptions=False)
    with capture_logs(processors=[merge_contextvars]) as logs:
        monkeypatch.setattr("wren.core.errors._log", structlog.get_logger())
        response = client.get("/boom", headers={REQUEST_ID_HEADER: "outer-corr-9"})

    assert response.status_code == 500
    assert _one(logs, "unhandled_exception")["request_id"] == "outer-corr-9"


async def test_non_http_scopes_pass_through_untouched() -> None:
    # Lifespan/websocket scopes reach the inner app unmodified and bind nothing;
    # only http requests get a request_id. Mirrors the StripInbound contract.
    seen: dict[str, object] = {}

    async def inner(scope: object, receive: object, send: object) -> None:
        seen["scope"] = scope

    middleware = CorrelationMiddleware(inner, service="wren-test")
    scope = {"type": "lifespan"}

    async def receive() -> dict[str, str]:
        return {}

    async def send(_message: object) -> None:
        return None

    await middleware(scope, receive, send)
    assert seen["scope"] is scope
    assert "request_id" not in structlog.contextvars.get_contextvars()
