"""Real-ASGI Sentry envelope tests for backend 500 ownership.

These exercise the actual FastAPI app through TestClient with a real Sentry SDK
client and a recording transport, proving exact ownership (one log, one
envelope), bounded metadata plus the process ``service`` tag, user isolation,
zero-event 4xx handling, and exception-chain PII scrubbing at the serialized
envelope boundary instead of by mocking the reporter.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import sentry_sdk
import structlog
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.identity import require_internal_user
from wren.core.settings import AppSettings
from wren.oauth.errors import OAuthError, OAuthErrorCode, build_oauth_exception_handlers
from wren_common import sentry as sentry_module

if TYPE_CHECKING:
    from sentry_sdk.envelope import Envelope

TEST_DSN = "https://testingkey@o0.ingest.sentry.io/1"
TEST_RELEASE = "0123456789abcdef0123456789abcdef01234567"

# Built by concatenation so the assembled sentinel strings never appear
# verbatim in this file's source: frame source-context lines inlined into the
# envelope would otherwise contain them and false-fail the scrub assertions.
SENTINEL_QUERY = "SENTINEL_" + "QUERY_TOKEN"
SENTINEL_HEADER = "SENTINEL_" + "HEADER_TOKEN"
SENTINEL_COOKIE = "SENTINEL_" + "COOKIE_TOKEN"
SENTINEL_CONNECT_MSG = "SENTINEL_" + "CONNECT_MSG"
SENTINELS = (SENTINEL_QUERY, SENTINEL_HEADER, SENTINEL_COOKIE, SENTINEL_CONNECT_MSG)
INTERNAL_HEADERS = {"X-Internal-Api-Token": "test-internal-token", "X-User-ID": "user-ada"}


class RecordingTransport(Transport):
    """Records post-``before_send`` event payloads instead of sending them."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, Any]] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        event = envelope.get_event()
        if event is not None:
            self.events.append(dict(event))


MakeSettings = Callable[..., AppSettings]


@pytest.fixture
def transport() -> RecordingTransport:
    recording = RecordingTransport()
    sentry_module._initialized = False
    sentry_module._disabled_logged = False
    sentry_module._SERVICE = None
    sentry_module._disabled_services.clear()
    sentry_sdk.init()
    assert sentry_module.initialize_sentry(
        dsn=TEST_DSN,
        environment="production",
        release=TEST_RELEASE,
        service="wren-external",
        transport=recording,
    )
    return recording


def _client(make_settings: MakeSettings, router: APIRouter, *, oauth: bool = False) -> TestClient:
    handlers: dict[Any, Any] = dict(build_exception_handlers())
    if oauth:
        handlers.update(build_oauth_exception_handlers())
    settings = make_settings(
        sentry_dsn=TEST_DSN,
        sentry_release=TEST_RELEASE,
        service="wren-external",
    )
    app = create_app(settings, routers=[router], exception_handlers=handlers)
    # create_app does not install the internal-token seam; the real processes do
    # it at startup wiring. Install it here so require_internal_user can resolve.
    app.state.internal_api_token = settings.internal_api_token
    return TestClient(app, raise_server_exceptions=False)


def _upstream_connect_error() -> httpx.ConnectError:
    """Build the failure at runtime; no sentinel value appears in raise-site source."""
    request = httpx.Request(
        "GET",
        "https://backend.internal.test/v1?token=" + SENTINEL_QUERY,
        headers={"authorization": "Bearer " + SENTINEL_HEADER},
        cookies={"session": SENTINEL_COOKIE},
    )
    return httpx.ConnectError(SENTINEL_CONNECT_MSG, request=request)


def _upstream_boom_router() -> APIRouter:
    router = APIRouter(tags=["roadmaps"])

    @router.get("/roadmaps/{roadmap_id}")
    async def get_roadmap(user_id: str = Depends(require_internal_user)) -> None:
        raise _upstream_connect_error()

    return router


def _mapped_internal_boom_router() -> APIRouter:
    router = APIRouter(tags=["roadmaps"])

    # The secret-bearing message is assembled at runtime: frame source-context
    # lines inlined into the envelope would otherwise contain its literal.
    @router.get("/roadmaps/{roadmap_id}/overview")
    async def get_overview(user_id: str = Depends(require_internal_user)) -> None:
        raise RuntimeError("secret database detail: postgres://admin:" + "hunter2" + "@host")

    return router


def _unmapped_boom_router() -> APIRouter:
    router = APIRouter()

    @router.get("/ops/unmapped-endpoint")
    async def boom() -> None:
        raise RuntimeError("unmapped infrastructure failure")

    return router


def _concurrent_boom_router() -> APIRouter:
    """Hold both requests at the handler boundary so their scopes overlap."""
    router = APIRouter(tags=["roadmaps"])
    arrived = 0
    release: asyncio.Event | None = None

    @router.get("/roadmaps/{roadmap_id}/overview")
    async def get_overview(user_id: str = Depends(require_internal_user)) -> None:
        nonlocal arrived, release
        if release is None:
            release = asyncio.Event()
        arrived += 1
        if arrived == 2:
            release.set()
        await asyncio.wait_for(release.wait(), timeout=2)
        raise RuntimeError("concurrent failure for resolved user")

    return router


def _routine_4xx_router() -> APIRouter:
    """One router mounting both a Wren 404 route and a request-validation route."""
    from pydantic import BaseModel

    from wren.core.errors import NotFound

    class _Item(BaseModel):
        title: str

    router = APIRouter()

    @router.get("/roadmaps/{roadmap_id}")
    async def not_found() -> None:
        raise NotFound("no roadmap secret-id-123")

    @router.post("/roadmaps")
    async def create(item: _Item) -> None:
        return None

    return router


def _oauth_error_router(*, status: int, error: OAuthErrorCode) -> APIRouter:
    router = APIRouter(tags=["oauth"])

    @router.post("/token")
    async def token() -> None:
        raise OAuthError(error, "protocol failure", status=status)

    return router


def _assert_problem_json_500(response: Any) -> None:
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "INTERNAL"
    assert body["detail"] == "An unexpected error occurred."


def test_mapped_authenticated_500_emits_exactly_one_log_and_envelope(
    make_settings: MakeSettings, transport: RecordingTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The catch-all handler passes its module logger into report_error, and the
    # configured processor chain caches on first use; a capturing double is the
    # reliable boundary here (same approach as the fault-log test in test_errors).
    cap = structlog.testing.CapturingLogger()
    monkeypatch.setattr("wren.core.errors._log", cap)

    client = _client(make_settings, _mapped_internal_boom_router())
    response = client.get("/roadmaps/r-123/overview", headers=INTERNAL_HEADERS)

    _assert_problem_json_500(response)
    fault_logs = [call for call in cap.calls if call.method_name == "error"]
    assert len(fault_logs) == 1
    assert fault_logs[0].args == ("unhandled_exception",)
    assert (
        fault_logs[0].kwargs["operation"]
        == "roadmaps.get_overview_roadmaps__roadmap_id__overview_get"
    )
    assert fault_logs[0].kwargs["domain"] == "roadmaps"
    assert isinstance(fault_logs[0].kwargs["exc_info"], RuntimeError)

    assert len(transport.events) == 1
    event = transport.events[0]
    assert event["release"] == f"wren-api@{TEST_RELEASE}"
    assert event["tags"]["operation"] == "roadmaps.get_overview_roadmaps__roadmap_id__overview_get"
    assert event["tags"]["domain"] == "roadmaps"
    assert event["tags"]["error_kind"] == "internal"
    assert event["tags"]["service"] == "wren-external"
    assert event["user"] == {"id": "user-ada"}
    assert event["fingerprint"] == [
        "roadmaps.get_overview_roadmaps__roadmap_id__overview_get",
        "internal",
        "{{ default }}",
    ]


def test_upstream_500_envelope_is_scrubbed_across_the_exception_chain(
    make_settings: MakeSettings, transport: RecordingTransport
) -> None:
    client = _client(make_settings, _upstream_boom_router())
    response = client.get("/roadmaps/r-123", headers=INTERNAL_HEADERS)

    _assert_problem_json_500(response)
    assert len(transport.events) == 1
    event = transport.events[0]
    assert event["tags"]["error_kind"] == "upstream"

    for field in ("request", "breadcrumbs", "extra", "message", "logentry"):
        assert field not in event
    values = event["exception"]["values"]
    assert [value["type"] for value in values] == ["ConnectError"]
    assert values[0]["value"] == "[Redacted exception]"
    assert "mechanism" not in values[0]
    serialized = json.dumps(event, default=str)
    for sentinel in SENTINELS:
        assert sentinel not in serialized
    assert "hunter2" not in serialized


def test_route_without_reporting_domain_uses_safe_500_operation(
    make_settings: MakeSettings, transport: RecordingTransport
) -> None:
    client = _client(make_settings, _unmapped_boom_router())
    response = client.get("/ops/unmapped-endpoint")

    _assert_problem_json_500(response)
    assert len(transport.events) == 1
    event = transport.events[0]
    assert event["tags"]["operation"] == "http.500"
    assert "domain" not in event["tags"]
    assert "user" not in event


def test_routine_4xx_emits_zero_envelopes(
    make_settings: MakeSettings,
    transport: RecordingTransport,
) -> None:
    client = _client(make_settings, _routine_4xx_router())
    response = client.get("/roadmaps/r-123")
    assert response.status_code == 404
    response = client.post("/roadmaps", json={})
    assert response.status_code == 422

    assert transport.events == []


def test_oauth_client_error_emits_zero_envelopes_and_server_error_one(
    make_settings: MakeSettings,
    transport: RecordingTransport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cap = structlog.testing.CapturingLogger()
    monkeypatch.setattr("wren_common.reporting.get_logger", lambda _name: cap)

    client = _client(
        make_settings,
        _oauth_error_router(status=400, error=OAuthErrorCode.INVALID_REQUEST),
        oauth=True,
    )
    response = client.post("/token")
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request", "error_description": "protocol failure"}
    assert transport.events == []
    assert cap.calls == []

    client = _client(
        make_settings,
        _oauth_error_router(status=500, error=OAuthErrorCode.SERVER_ERROR),
        oauth=True,
    )
    response = client.post("/token")
    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"error": "server_error", "error_description": "protocol failure"}

    fault_logs = [call for call in cap.calls if call.method_name == "error"]
    assert len(fault_logs) == 1
    assert fault_logs[0].args == ("unhandled_exception",)
    assert len(transport.events) == 1
    event = transport.events[0]
    assert event["tags"]["operation"] == "oauth.token_token_post"
    assert event["tags"]["domain"] == "oauth"
    assert event["tags"]["service"] == "wren-external"


def test_sequential_backend_users_are_isolated_in_envelopes(
    make_settings: MakeSettings, transport: RecordingTransport
) -> None:
    client = _client(make_settings, _mapped_internal_boom_router())
    for user_id in ("user-ada", "user-grace"):
        response = client.get(
            "/roadmaps/r-123/overview", headers={**INTERNAL_HEADERS, "X-User-ID": user_id}
        )
        _assert_problem_json_500(response)

    assert [event.get("user") for event in transport.events] == [
        {"id": "user-ada"},
        {"id": "user-grace"},
    ]


def test_concurrent_backend_users_are_isolated_in_envelopes(
    make_settings: MakeSettings, transport: RecordingTransport
) -> None:
    client = _client(make_settings, _concurrent_boom_router())

    def request_for(user_id: str) -> int:
        response = client.get(
            "/roadmaps/r-123/overview", headers={**INTERNAL_HEADERS, "X-User-ID": user_id}
        )
        return int(response.status_code)

    with client, ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(request_for, ("user-ada", "user-grace")))

    assert statuses == [500, 500]
    assert sorted(event["user"]["id"] for event in transport.events) == [
        "user-ada",
        "user-grace",
    ]
