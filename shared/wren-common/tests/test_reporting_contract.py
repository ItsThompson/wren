from __future__ import annotations

from unittest.mock import Mock, patch

from wren_common.reporting import Domain, Kind, LogEvent, ReportLevel, report_error


def test_report_error_logs_contract_and_forwards_scope() -> None:
    logger = Mock()
    exception = RuntimeError("database unavailable")
    with (
        patch("wren_common.reporting.get_logger", return_value=logger),
        patch("wren_common.sentry.report_exception") as report,
    ):
        report_error(
            exception,
            operation="roadmaps.create",
            domain=Domain.ROADMAPS,
            kind=Kind.DATABASE,
            user_id="user-1",
            log_event=LogEvent.UNHANDLED_EXCEPTION,
            level=ReportLevel.ERROR,
            bounded_tags={"component": "writer"},
            context_data={"query": "roadmap"},
            group_key="roadmaps.create",
            group_exact=True,
        )

    logger.error.assert_called_once()
    assert logger.error.call_args.args == ("unhandled_exception",)
    report.assert_called_once()
    assert report.call_args.kwargs["tags"]["operation"] == "roadmaps.create"
    assert report.call_args.kwargs["context"] == {"query": "roadmap"}
    assert report.call_args.kwargs["fingerprint"] == ["roadmaps.create"]


def test_report_error_drops_invalid_closed_contract_values() -> None:
    logger = Mock()
    with (
        patch("wren_common.reporting.get_logger", return_value=logger),
        patch("wren_common.sentry.report_exception") as report,
    ):
        report_error(
            RuntimeError("boom"),
            operation="roadmaps.create",
            domain="not-a-domain",
            kind="internal",
            user_id=None,
            log_event="not-a-log-event",
            level="error",
            bounded_tags={},
            context_data={},
            group_key="roadmaps.create",
            group_exact=False,
        )

    assert logger.mock_calls == []
    report.assert_not_called()


def test_report_error_uses_http_500_for_invalid_operation() -> None:
    logger = Mock()
    with (
        patch("wren_common.reporting.get_logger", return_value=logger),
        patch("wren_common.sentry.report_exception") as report,
    ):
        report_error(
            RuntimeError("boom"),
            operation="/roadmaps/{id}",
            domain=Domain.ROADMAPS,
            kind=Kind.INTERNAL,
            user_id=None,
            log_event=LogEvent.UNHANDLED_EXCEPTION,
            level=ReportLevel.ERROR,
            bounded_tags={},
            context_data={},
            group_key="/roadmaps/{id}",
            group_exact=True,
        )

    assert report.call_args.kwargs["tags"]["operation"] == "http.500"
    assert report.call_args.kwargs["fingerprint"] == ["http.500"]
