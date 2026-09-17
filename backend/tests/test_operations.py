"""Backend route-operation reporting adapter tests."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
import sqlalchemy.exc
import structlog
from starlette.requests import Request

from wren.core.operations import _error_kind, operation_for_request, report_backend_failure
from wren_common.reporting import Domain, Kind, LogEvent, ReportLevel


def _request(path: str, *, route_path: str | None = None) -> Request:
    scope: dict[str, object] = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "route": SimpleNamespace(path=route_path) if route_path is not None else None,
    }
    return Request(scope)


def test_operation_uses_the_matched_route_template() -> None:
    request = _request("/roadmaps/r-123", route_path="/roadmaps/{roadmap_id}")

    assert operation_for_request(request) == "roadmaps.get"


def test_unmatched_route_uses_safe_500_operation() -> None:
    request = _request("/roadmaps/r-123")

    assert operation_for_request(request) == "http.500"


@pytest.mark.parametrize(
    ("exception", "kind"),
    [
        (TimeoutError("timed out"), Kind.TIMEOUT),
        (httpx.ReadTimeout("timed out"), Kind.TIMEOUT),
        (sqlalchemy.exc.OperationalError("select", {}, RuntimeError("db")), Kind.DATABASE),
        (httpx.ConnectError("upstream"), Kind.UPSTREAM),
    ],
)
def test_error_kind_prefers_timeout_then_database_then_httpx(
    exception: BaseException, kind: Kind
) -> None:
    assert _error_kind(exception) is kind


def test_backend_report_emits_non_internal_error_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request("/roadmaps/r-123", route_path="/roadmaps/{roadmap_id}")
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wren.core.operations.report_error",
        lambda exception, **kwargs: calls.append({"exception": exception, **kwargs}),
    )

    report_backend_failure(request, httpx.ReadTimeout("timed out"))

    call = calls[0]
    assert call["kind"] is Kind.TIMEOUT
    assert call["context_data"]["error_kind"] == "timeout"  # type: ignore[index]


def test_backend_report_passes_bounded_context_and_typed_taxonomy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request("/roadmaps/r-123", route_path="/roadmaps/{roadmap_id}")
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wren.core.operations.report_error",
        lambda exception, **kwargs: calls.append({"exception": exception, **kwargs}),
    )
    structlog.contextvars.bind_contextvars(user_id="user-ada")
    try:
        exception = RuntimeError("private database detail")
        report_backend_failure(request, exception)
    finally:
        structlog.contextvars.clear_contextvars()

    assert len(calls) == 1
    call = calls[0]
    assert call["exception"] is exception
    assert call["operation"] == "roadmaps.get"
    assert call["domain"] is Domain.ROADMAPS
    assert call["kind"] is Kind.INTERNAL
    assert call["log_event"] is LogEvent.UNHANDLED_EXCEPTION
    assert call["level"] is ReportLevel.ERROR
    assert call["user_id"] == "user-ada"
    assert call["context_data"] == {
        "method": "GET",
        "path": "/roadmaps/{roadmap_id}",
        "template": "/roadmaps/{roadmap_id}",
        "status": 500,
    }
    assert "r-123" not in repr(call["context_data"])
    assert call["group_key"] == "roadmaps.get"
    assert call["group_exact"] is True
