"""MCP boundary reporting tests."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import sentry_sdk
from mcp.server.fastmcp.exceptions import ToolError
from sentry_sdk.transport import Transport

from wren_common import sentry as sentry_module
from wren_common.limiter import ReportLimiter
from wren_common.reporting import Domain, Kind, LogEvent, ReportLevel, report_error
from wren_mcp import reporting
from wren_mcp.tool_errors import (
    BackendToolError,
    BackendUnavailableToolError,
    raise_for_problem,
)
from wren_mcp.tool_metrics import count_invocations
from wren_mcp.tool_registry import counted_tool_registrar, registered_tool_names

if TYPE_CHECKING:
    from sentry_sdk.envelope import Envelope

TEST_DSN = "https://testingkey@o0.ingest.sentry.io/1"
TEST_RELEASE = "0123456789abcdef0123456789abcdef01234567"

SENTINEL_QUERY = "SENTINEL_QUERY_TOKEN"
SENTINEL_HEADER = "SENTINEL_HEADER_TOKEN"
SENTINEL_COOKIE = "SENTINEL_COOKIE_TOKEN"
SENTINELS = (SENTINEL_QUERY, SENTINEL_HEADER, SENTINEL_COOKIE, "SENTINEL_CONNECT_MSG")


class RecordingTransport(Transport):
    """Records post-``before_send`` event payloads instead of sending them."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, Any]] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        event = envelope.get_event()
        if event is not None:
            self.events.append(dict(event))


class _DiagnosticLogger:
    def __init__(self, diagnostics: list[dict[str, object]]) -> None:
        self._diagnostics = diagnostics

    def error(self, event: str, **kwargs: object) -> None:
        self._diagnostics.append({event: kwargs})

    def warning(self, event: str, **kwargs: object) -> None:
        self._diagnostics.append({event: kwargs})


def test_backend_problem_is_recoverable_without_operational_reporting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[BaseException, dict[str, object]]] = []
    diagnostics: list[dict[str, object]] = []

    monkeypatch.setattr(
        "wren_mcp.tool_errors.report_mcp_error",
        lambda exception, **kwargs: calls.append((exception, kwargs)),
        raising=False,
    )
    monkeypatch.setattr(
        reporting,
        "_log",
        type(
            "DiagnosticLogger",
            (),
            {"warning": lambda _, event, **kwargs: diagnostics.append({event: kwargs})},
        )(),
    )
    response = httpx.Response(500, json={"code": "INTERNAL", "detail": "service failed"})

    with pytest.raises(BackendToolError) as excinfo:
        raise_for_problem(response)

    assert isinstance(excinfo.value, ToolError)
    assert calls == []
    assert diagnostics == []


async def test_transport_failure_is_reported_once_by_the_tool_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wren_mcp.tool_metrics.report_mcp_error",
        lambda exception, **kwargs: calls.append({"exception": exception, **kwargs}),
    )

    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    mcp = FastMCP("metrics-test")
    tool = counted_tool_registrar(mcp)

    @tool(ToolAnnotations(title="Metrics test"))
    async def failing_tool() -> None:
        raise BackendUnavailableToolError("retry", kind="timeout")

    wrapped = count_invocations(failing_tool)
    with pytest.raises(BackendUnavailableToolError):
        await wrapped()

    assert len(calls) == 1
    assert calls[0]["kind_name"] == "timeout"


async def test_expected_backend_error_is_not_reported_by_the_tool_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wren_mcp.tool_metrics.report_mcp_error",
        lambda exception, **kwargs: calls.append({"exception": exception, **kwargs}),
    )

    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    mcp = FastMCP("metrics-expected-test")
    tool = counted_tool_registrar(mcp)

    @tool(ToolAnnotations(title="Expected error test"))
    async def expected_tool() -> None:
        raise BackendToolError("retry the request", status_code=409, code="STALE_REVISION")

    wrapped = count_invocations(expected_tool)
    with pytest.raises(BackendToolError):
        await wrapped()

    assert calls == []


def test_unregistered_wrapper_rejects_before_observability_side_effects() -> None:
    async def unregistered_tool() -> None:
        return None

    with pytest.raises(ValueError, match="registered as an MCP tool"):
        count_invocations(unregistered_tool)


def test_backend_response_is_not_reported_as_an_operational_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        reporting,
        "report_error",
        lambda exception, **kwargs: calls.append({"exception": exception, **kwargs}),
    )
    reporting._MCP_REPORT_LIMITERS = {
        key: ReportLimiter(limit=1, window_seconds=3_600.0)
        for key in ("upstream", "timeout", "internal")
    }

    error = BackendToolError("backend failed", status_code=500, code="INTERNAL")
    reporting.report_mcp_error(
        error,
        operation_name="mcp.backend_error",
        kind_name="upstream",
        log_event_name="backend_error",
        level_name="error",
    )

    assert calls == []


def test_shared_adapter_limits_each_failure_class_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        reporting,
        "report_error",
        lambda exception, **kwargs: calls.append({"exception": exception, **kwargs}),
    )
    reporting._MCP_REPORT_LIMITERS = {
        key: ReportLimiter(limit=1, window_seconds=3_600.0)
        for key in ("upstream", "timeout", "internal")
    }

    for kind in ("upstream", "upstream", "internal", "internal"):
        reporting.report_mcp_error(
            RuntimeError(kind),
            operation_name="mcp.internal_request",
            kind_name=kind,
            log_event_name="unhandled_exception",
            level_name="error",
        )

    assert len(calls) == 2
    assert [call["group_key"] for call in calls] == ["mcp.upstream", "mcp.internal"]
    assert calls[0]["context_data"] == {"error_kind": "upstream"}


def test_unregistered_tool_operation_is_not_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    monkeypatch.setattr(
        reporting,
        "report_error",
        lambda exception, **kwargs: calls.append({"exception": exception, **kwargs}),
    )
    monkeypatch.setattr(
        reporting,
        "_log",
        type(
            "DiagnosticLogger",
            (),
            {"warning": lambda _, event, **kwargs: diagnostics.append({event: kwargs})},
        )(),
        raising=False,
    )

    reporting.report_mcp_error(
        RuntimeError("transport failed"),
        operation_name="tool.not_registered",
        kind_name="upstream",
        log_event_name="unhandled_exception",
        level_name="error",
    )

    assert calls == []
    assert diagnostics == [{"reporting_contract_invalid": {"fields": ["operation"]}}]


@pytest.mark.parametrize(
    ("field", "metadata"),
    [
        ("kind", {"kind_name": "not_a_kind"}),
        ("log_event", {"log_event_name": "not_a_log_event"}),
        ("level", {"level_name": "not_a_level"}),
    ],
)
def test_invalid_required_metadata_is_not_reported_and_logs_only_field_name(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    metadata: dict[str, str],
) -> None:
    calls: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    monkeypatch.setattr(
        reporting,
        "report_error",
        lambda exception, **kwargs: calls.append({"exception": exception, **kwargs}),
    )
    monkeypatch.setattr(
        reporting,
        "_log",
        type(
            "DiagnosticLogger",
            (),
            {"warning": lambda _, event, **kwargs: diagnostics.append({event: kwargs})},
        )(),
        raising=False,
    )

    reporting.report_mcp_error(
        RuntimeError("transport failed"),
        operation_name="mcp.internal_request",
        kind_name=metadata.get("kind_name", "upstream"),
        log_event_name=metadata.get("log_event_name", "unhandled_exception"),
        level_name=metadata.get("level_name", "error"),
    )

    assert calls == []
    assert diagnostics == [{"reporting_contract_invalid": {"fields": [field]}}]


def test_registrar_adds_tool_name_to_report_registry() -> None:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    mcp = FastMCP("registry-test")
    tool = counted_tool_registrar(mcp)

    @tool(ToolAnnotations(title="Registry test"))
    async def registry_probe() -> None:
        return None

    assert "registry_probe" in registered_tool_names()


def test_shared_adapter_uses_typed_taxonomy_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from wren_mcp import reporting

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        reporting,
        "report_error",
        lambda exception, **kwargs: calls.append({"exception": exception, **kwargs}),
    )

    exception = RuntimeError("transport failed")
    reporting.report_mcp_error(
        exception,
        operation_name="mcp.internal_request",
        kind_name="timeout",
        log_event_name="unhandled_exception",
        level_name="error",
        user_id="user-ada",
        bounded_tags={"method": "GET"},
        context_data={"method": "GET", "status": 503},
    )

    assert len(calls) == 1
    report = calls[0]
    assert report["exception"] is exception
    assert report["operation"] == "mcp.internal_request"
    assert report["domain"] is Domain.MCP
    assert report["kind"] is Kind.TIMEOUT
    assert report["log_event"] is LogEvent.UNHANDLED_EXCEPTION
    assert report["level"] is ReportLevel.ERROR
    assert report["user_id"] == "user-ada"


def _reset_limiters() -> None:
    reporting._MCP_REPORT_LIMITERS = {
        key: ReportLimiter(limit=1, window_seconds=3_600.0)
        for key in ("upstream", "timeout", "internal")
    }


def test_caller_tool_tag_disagreeing_with_operation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    calls: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    monkeypatch.setattr(
        reporting,
        "report_error",
        lambda exception, **kwargs: calls.append({"exception": exception, **kwargs}),
    )
    monkeypatch.setattr(
        reporting,
        "_log",
        _DiagnosticLogger(diagnostics),
        raising=False,
    )

    mcp = FastMCP("tool-tag-mismatch-test")
    tool = counted_tool_registrar(mcp)

    @tool(ToolAnnotations(title="Tool tag mismatch test"))
    async def mismatch_tool() -> None:
        return None

    reporting.report_mcp_error(
        RuntimeError("transport failed"),
        operation_name="tool.mismatch_tool",
        kind_name="upstream",
        log_event_name="unhandled_exception",
        level_name="error",
        bounded_tags={"tool": "some_other_tool"},
    )

    assert calls == []
    assert diagnostics == [{"reporting_contract_invalid": {"fields": ["tool"]}}]


def test_caller_tool_tag_on_non_tool_operation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    monkeypatch.setattr(
        reporting,
        "report_error",
        lambda exception, **kwargs: calls.append({"exception": exception, **kwargs}),
    )
    monkeypatch.setattr(
        reporting,
        "_log",
        _DiagnosticLogger(diagnostics),
        raising=False,
    )

    reporting.report_mcp_error(
        RuntimeError("internal failure"),
        operation_name="mcp.internal_request",
        kind_name="internal",
        log_event_name="unhandled_exception",
        level_name="error",
        bounded_tags={"tool": "some_tool"},
    )

    assert calls == []
    assert diagnostics == [{"reporting_contract_invalid": {"fields": ["tool"]}}]


def test_shared_report_error_rejects_tool_operations_without_registry() -> None:
    diagnostics: list[dict[str, object]] = []
    logger = _DiagnosticLogger(diagnostics)

    report_error(
        RuntimeError("transport failed"),
        operation="tool.arbitrary",
        domain=Domain.MCP,
        kind=Kind.UPSTREAM,
        user_id=None,
        log_event=LogEvent.UNHANDLED_EXCEPTION,
        level=ReportLevel.WARNING,
        bounded_tags={"tool": "arbitrary"},
        context_data=None,
        group_key=None,
        group_exact=False,
        logger=logger,
    )

    assert len(diagnostics) == 2
    fault_fields = diagnostics[0]["unhandled_exception"]
    assert isinstance(fault_fields, dict)
    assert isinstance(fault_fields["exc_info"], RuntimeError)
    assert diagnostics[1] == {"reporting_contract_invalid": {"fields": ["operation"]}}


async def test_registered_tool_failure_reaches_transport_as_one_scrubbed_envelope() -> None:
    import structlog
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    transport = RecordingTransport()
    sentry_module._initialized = False
    sentry_module._SERVICE = None
    sentry_module._disabled_services.clear()
    sentry_sdk.init()
    assert sentry_module.initialize_sentry(
        dsn=TEST_DSN,
        environment="production",
        release=TEST_RELEASE,
        service="wren-mcp",
        transport=transport,
    )
    _reset_limiters()

    mcp = FastMCP("envelope-test")
    tool = counted_tool_registrar(mcp)

    request = httpx.Request(
        "GET",
        f"https://backend.internal.test/v1?token={SENTINEL_QUERY}",
        headers={"authorization": f"Bearer {SENTINEL_HEADER}"},
        cookies={"session": SENTINEL_COOKIE},
    )
    connect = httpx.ConnectError("SENTINEL_CONNECT_MSG", request=request)
    unavailable = BackendUnavailableToolError("retry later", kind="upstream")
    unavailable.__cause__ = connect

    @tool(ToolAnnotations(title="Envelope test"))
    async def envelope_tool() -> None:
        raise unavailable

    structlog.contextvars.bind_contextvars(user_id="user-ada")
    try:
        wrapped = count_invocations(envelope_tool)
        with pytest.raises(BackendUnavailableToolError) as excinfo:
            await wrapped()
    finally:
        structlog.contextvars.clear_contextvars()

    # The rethrown object is unchanged, including its original HTTPX cause.
    assert excinfo.value is unavailable
    assert unavailable.__cause__ is connect

    assert len(transport.events) == 1
    event = transport.events[0]
    assert event["release"] == f"wren-mcp@{TEST_RELEASE}"
    assert event["tags"]["operation"] == "tool.envelope_tool"
    assert event["tags"]["domain"] == "mcp"
    assert event["tags"]["error_kind"] == "upstream"
    assert event["tags"]["tool"] == "envelope_tool"
    assert event["tags"]["service"] == "wren-mcp"
    assert event["user"] == {"id": "user-ada"}
    assert event["fingerprint"] == ["mcp.upstream"]

    values = event["exception"]["values"]
    assert [value["type"] for value in values] == ["ConnectError", "BackendUnavailableToolError"]
    for value in values:
        assert value["value"] == "[Redacted exception]"
        assert "mechanism" not in value
    serialized = json.dumps(event, default=str)
    for sentinel in SENTINELS:
        assert sentinel not in serialized

    # A second registered tool failing with the same class uses the same exact
    # per-class group while its bounded tool tag differs.
    _reset_limiters()

    @tool(ToolAnnotations(title="Envelope test two"))
    async def second_tool() -> None:
        raise BackendUnavailableToolError("retry later too", kind="upstream")

    with pytest.raises(BackendUnavailableToolError):
        await count_invocations(second_tool)()

    assert len(transport.events) == 2
    assert transport.events[1]["tags"]["tool"] == "second_tool"
    assert transport.events[1]["fingerprint"] == ["mcp.upstream"]


async def test_sequential_tool_users_are_isolated_in_envelopes() -> None:
    import structlog
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    transport = RecordingTransport()
    sentry_module._initialized = False
    sentry_module._SERVICE = None
    sentry_module._disabled_services.clear()
    sentry_sdk.init()
    assert sentry_module.initialize_sentry(
        dsn=TEST_DSN,
        environment="production",
        release=TEST_RELEASE,
        service="wren-mcp",
        transport=transport,
    )
    _reset_limiters()

    mcp = FastMCP("user-isolation-test")
    tool = counted_tool_registrar(mcp)

    @tool(ToolAnnotations(title="User isolation test"))
    async def isolation_tool() -> None:
        raise BackendUnavailableToolError("retry later", kind="upstream")

    wrapped = count_invocations(isolation_tool)
    for user_id in ("user-ada", "user-grace"):
        structlog.contextvars.bind_contextvars(user_id=user_id)
        try:
            with pytest.raises(BackendUnavailableToolError):
                await wrapped()
        finally:
            structlog.contextvars.clear_contextvars()
        _reset_limiters()

    assert [event.get("user") for event in transport.events] == [
        {"id": "user-ada"},
        {"id": "user-grace"},
    ]


async def test_concurrent_tool_users_are_isolated_in_envelopes() -> None:
    import structlog
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    transport = RecordingTransport()
    sentry_module._initialized = False
    sentry_module._SERVICE = None
    sentry_module._disabled_services.clear()
    sentry_sdk.init()
    assert sentry_module.initialize_sentry(
        dsn=TEST_DSN,
        environment="production",
        release=TEST_RELEASE,
        service="wren-mcp",
        transport=transport,
    )
    reporting._MCP_REPORT_LIMITERS = {
        "upstream": ReportLimiter(limit=2, window_seconds=3_600.0),
        "timeout": ReportLimiter(limit=1, window_seconds=3_600.0),
        "internal": ReportLimiter(limit=1, window_seconds=3_600.0),
    }

    mcp = FastMCP("concurrent-user-isolation-test")
    tool = counted_tool_registrar(mcp)
    arrived = 0
    release = asyncio.Event()

    @tool(ToolAnnotations(title="Concurrent user isolation test"))
    async def concurrent_isolation_tool() -> None:
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            release.set()
        await asyncio.wait_for(release.wait(), timeout=2)
        raise BackendUnavailableToolError("retry later", kind="upstream")

    wrapped = count_invocations(concurrent_isolation_tool)

    async def invoke(user_id: str) -> None:
        structlog.contextvars.bind_contextvars(user_id=user_id)
        try:
            with pytest.raises(BackendUnavailableToolError):
                await wrapped()
        finally:
            structlog.contextvars.clear_contextvars()

    await asyncio.gather(invoke("user-ada"), invoke("user-grace"))

    assert sorted(event["user"]["id"] for event in transport.events) == [
        "user-ada",
        "user-grace",
    ]
