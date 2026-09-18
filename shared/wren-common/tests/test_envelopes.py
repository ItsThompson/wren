"""Real-SDK recording-transport envelope tests.

These prove the primary shared contracts against the actual ``sentry_sdk``
options (scrubber, release naming, disabled integrations) by inspecting
serialized post-``before_send`` envelopes instead of mocking capture calls:
exception-chain and request PII scrubbing, the process ``service`` tag, user
isolation, and disabled-DSN zero-transport behavior.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from wren_common import sentry as sentry_module
from wren_common.reporting import Domain, Kind, LogEvent, ReportLevel, report_error

if TYPE_CHECKING:
    from sentry_sdk.envelope import Envelope

TEST_DSN = "https://testingkey@o0.ingest.sentry.io/1"

SENTINEL_QUERY = "SENTINEL_QUERY_TOKEN"
SENTINEL_HEADER = "SENTINEL_HEADER_TOKEN"
SENTINEL_COOKIE = "SENTINEL_COOKIE_TOKEN"
SENTINEL_BODY = "SENTINEL_BODY_TOKEN"
SENTINELS = (
    SENTINEL_QUERY,
    SENTINEL_HEADER,
    SENTINEL_COOKIE,
    SENTINEL_BODY,
    "SENTINEL_CAUSE_MSG",
    "SENTINEL_CONNECT_MSG",
    "SENTINEL_OUTER_MSG",
)


class RecordingTransport(Transport):
    """Records post-``before_send`` event payloads instead of sending them."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, Any]] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        event = envelope.get_event()
        if event is not None:
            self.events.append(dict(event))


@pytest.fixture(autouse=True)
def reset_sentry_state() -> None:
    sentry_module._initialized = False
    sentry_module._disabled_logged = False
    sentry_module._SERVICE = None
    sentry_module._disabled_services.clear()
    # Re-init with no DSN so a client from an earlier test cannot capture.
    sentry_sdk.init()


def _init(
    transport: Transport,
    *,
    service: str = "wren-external",
    release: str = "0123456789abcdef0123456789abcdef01234567",
) -> None:
    assert sentry_module.initialize_sentry(
        dsn=TEST_DSN,
        environment="production",
        release=release,
        service=service,
        transport=transport,
    )


def _report(exception: BaseException, *, user_id: str | None = "user-1") -> None:
    report_error(
        exception,
        operation="roadmaps.get",
        domain=Domain.ROADMAPS,
        kind=Kind.UPSTREAM,
        user_id=user_id,
        log_event=LogEvent.UNHANDLED_EXCEPTION,
        level=ReportLevel.ERROR,
        bounded_tags=None,
        context_data={"method": "GET", "status": 502},
        group_key="roadmaps.get",
        group_exact=True,
    )


def _sentinel_exception() -> tuple[RuntimeError, httpx.ConnectError, ValueError]:
    """A three-level chain whose members carry request-derived sentinel data."""
    request = httpx.Request(
        "GET",
        f"https://backend.internal.test/v1/roadmaps?token={SENTINEL_QUERY}",
        headers={"authorization": f"Bearer {SENTINEL_HEADER}"},
        cookies={"session": SENTINEL_COOKIE},
        content=SENTINEL_BODY,
    )
    root = ValueError("SENTINEL_CAUSE_MSG")
    connect = httpx.ConnectError("SENTINEL_CONNECT_MSG", request=request)
    connect.__cause__ = root
    outer = RuntimeError("SENTINEL_OUTER_MSG")
    outer.__cause__ = connect
    return outer, connect, root


def _serialized(event: dict[str, Any]) -> str:
    return json.dumps(event, default=str)


@pytest.mark.parametrize("service", ["wren-external", "wren-internal", "wren-mcp"])
def test_every_envelope_carries_the_process_service_tag(service: str) -> None:
    transport = RecordingTransport()
    _init(transport, service=service)

    _report(RuntimeError("boom"))

    assert len(transport.events) == 1
    assert transport.events[0]["tags"]["service"] == service


def test_envelope_keeps_bounded_metadata_and_scrubs_the_exception_chain() -> None:
    transport = RecordingTransport()
    _init(transport)
    exception, connect, root = _sentinel_exception()

    _report(exception)

    assert len(transport.events) == 1
    event = transport.events[0]
    # Bounded operational metadata survives; identity is only the resolved ID.
    assert event["release"] == "wren-api@0123456789abcdef0123456789abcdef01234567"
    assert event["environment"] == "production"
    assert event["tags"]["operation"] == "roadmaps.get"
    assert event["tags"]["domain"] == "roadmaps"
    assert event["tags"]["error_kind"] == "upstream"
    assert event["user"] == {"id": "user-1"}
    assert event["level"] == "error"

    # Request-derived payload channels are gone entirely.
    for field in ("request", "breadcrumbs", "extra", "message", "logentry"):
        assert field not in event

    # Exception types and frames survive; values and mechanism data do not.
    values = event["exception"]["values"]
    assert [value["type"] for value in values] == ["ValueError", "ConnectError", "RuntimeError"]
    for value in values:
        assert value["value"] == "[Redacted exception]"
        assert "mechanism" not in value
        for frame in value.get("stacktrace", {}).get("frames", []):
            assert "vars" not in frame

    # No sentinel from the request, its chain, or a local reaches the envelope.
    serialized = _serialized(event)
    for sentinel in SENTINELS:
        assert sentinel not in serialized

    # The application exception object is untouched by reporting.
    assert exception.__cause__ is connect
    assert connect.__cause__ is root


def test_parent_scope_metadata_cannot_enter_a_report_envelope() -> None:
    transport = RecordingTransport()
    _init(transport)

    with sentry_sdk.isolation_scope() as parent_scope:
        parent_scope.set_tag("component", SENTINEL_HEADER)
        parent_scope.set_tag("unsafe", SENTINEL_QUERY)
        parent_scope.set_context(
            "report",
            {"secret": SENTINEL_QUERY, "nested": {"body": SENTINEL_BODY}},
        )
        parent_scope.set_user({"id": SENTINEL_COOKIE, "email": SENTINEL_HEADER})
        parent_scope.set_extra("request_body", SENTINEL_BODY)
        _report(RuntimeError("boom"), user_id=None)

    assert len(transport.events) == 1
    event = transport.events[0]
    assert event["contexts"] == {"report": {"method": "GET", "status": 502}}
    assert "component" not in event["tags"]
    assert "unsafe" not in event["tags"]
    assert "user" not in event
    serialized = _serialized(event)
    for sentinel in SENTINELS:
        assert sentinel not in serialized


def test_sequential_reports_isolate_user_identity() -> None:
    transport = RecordingTransport()
    _init(transport)

    _report(RuntimeError("first"), user_id="user-ada")
    _report(RuntimeError("second"), user_id="user-grace")
    _report(RuntimeError("third"), user_id=None)

    assert [event.get("user") for event in transport.events] == [
        {"id": "user-ada"},
        {"id": "user-grace"},
        None,
    ]


def test_empty_dsn_never_touches_the_transport() -> None:
    transport = RecordingTransport()

    assert (
        sentry_module.initialize_sentry(
            dsn="   ",
            environment="production",
            release="abc123def",
            service="wren-external",
            transport=transport,
        )
        is False
    )
    _report(RuntimeError("boom"))

    assert transport.events == []
    assert sentry_module._SERVICE is None
