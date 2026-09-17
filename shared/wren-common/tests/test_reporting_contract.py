from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from wren_common.reporting import (
    Domain,
    Kind,
    LogEvent,
    ReportingContractError,
    ReportLevel,
    make_reporting_contract,
    report_error,
)
from wren_common.reporting_types import sanitize_context, sanitize_tags


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
    assert report.call_args.kwargs["context"] == {}
    assert report.call_args.kwargs["tags"]["error_kind"] == "RuntimeError"
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

    logger.warning.assert_called_once_with(
        "reporting_contract_invalid", fields=["domain", "log_event"]
    )
    report.assert_not_called()


def test_report_error_skips_invalid_operation_and_emits_field_names_only() -> None:
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

    logger.warning.assert_called_once_with(
        "reporting_contract_invalid", fields=["operation", "domain"]
    )
    report.assert_not_called()


def test_contract_factory_enforces_operation_domain_pair() -> None:
    with pytest.raises(ReportingContractError) as error:
        make_reporting_contract(
            operation="oauth.token",
            domain=Domain.ROADMAPS,
            kind=Kind.INTERNAL,
            log_event=LogEvent.UNHANDLED_EXCEPTION,
            level=ReportLevel.ERROR,
        )

    assert error.value.fields == ("operation", "domain")


def test_optional_tags_are_allowlisted_and_bounded() -> None:
    result = sanitize_tags(
        {
            "component": "x" * 300,
            "operation": "caller-cannot-override",
            "unknown": "not accepted",
        }
    )

    assert result == {"component": "x" * 200}


def test_context_is_allowlisted_and_size_bounded() -> None:
    result = sanitize_context({"path": "x" * 20_000, "query": "secret"})

    assert "query" not in result
    assert len(str(result["path"])) < 8 * 1024
