"""MCP boundary reporting tests."""

from __future__ import annotations

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from wren_common.reporting import Domain, Kind, LogEvent, ReportLevel
from wren_mcp.tool_errors import BackendToolError, raise_for_problem


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
