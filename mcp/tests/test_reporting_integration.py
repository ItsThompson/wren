"""MCP boundary reporting tests."""

from __future__ import annotations

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from wren_common.limiter import ReportLimiter
from wren_common.reporting import Domain, Kind, LogEvent, ReportLevel
from wren_mcp import reporting
from wren_mcp.tool_errors import BackendToolError, BackendUnavailableToolError, raise_for_problem
from wren_mcp.tool_metrics import count_invocations


def test_backend_problem_reports_the_same_typed_error_before_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[BaseException, dict[str, object]]] = []

    def capture(exception: BaseException, **kwargs: object) -> None:
        calls.append((exception, kwargs))

    monkeypatch.setattr("wren_mcp.tool_errors.report_mcp_error", capture)
    response = httpx.Response(500, json={"code": "INTERNAL", "detail": "service failed"})

    with pytest.raises(BackendToolError) as excinfo:
        raise_for_problem(response)

    assert len(calls) == 1
    exception, report = calls[0]
    assert exception is excinfo.value
    assert isinstance(exception, ToolError)
    assert report["operation_name"] == "mcp.backend_error"
    assert report["kind_name"] == "upstream"
    assert report["log_event_name"] == "backend_error"
    assert report["level_name"] == "error"
    assert report["context_data"] == {"status": 500}
    assert report["bounded_tags"] == {"status": "500", "code": "INTERNAL"}


async def test_transport_failure_is_reported_once_by_the_tool_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wren_mcp.tool_metrics.report_mcp_error",
        lambda exception, **kwargs: calls.append({"exception": exception, **kwargs}),
    )

    async def failing_tool() -> None:
        raise BackendUnavailableToolError("retry", kind="timeout")

    wrapped = count_invocations(failing_tool)
    with pytest.raises(BackendUnavailableToolError):
        await wrapped()

    assert len(calls) == 1
    assert calls[0]["kind_name"] == "timeout"


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
            operation_name="tool.example",
            kind_name=kind,
            log_event_name="unhandled_exception",
            level_name="error",
        )

    assert len(calls) == 2
    assert [call["group_key"] for call in calls] == ["mcp.upstream", "mcp.internal"]
    assert calls[0]["context_data"] == {"error_kind": "upstream"}


def test_shared_adapter_uses_valid_taxonomy_fallbacks(
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
        log_event_name="backend_unavailable",
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
