from __future__ import annotations

import json
from typing import cast
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
from wren_common.reporting_types import (
    CONTEXT_ORIGINAL_BYTES_KEY,
    CONTEXT_TRUNCATED_KEY,
    MAX_CONTEXT_BYTES,
    SafeContext,
    sanitize_context,
    sanitize_tags,
)


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
            bounded_tags={"component": "writer", "error_kind": "timeout"},
            context_data={"query": "roadmap"},
            group_key="roadmaps.create",
            group_exact=True,
        )

    logger.error.assert_called_once()
    assert logger.error.call_args.args == ("unhandled_exception",)
    report.assert_called_once()
    assert report.call_args.kwargs["tags"] == {"component": "writer"}
    assert report.call_args.kwargs["context"] == {}
    assert report.call_args.kwargs["error_kind"] == "database"
    assert report.call_args.kwargs["fingerprint"] == [
        "roadmaps.create",
        "database",
        "{{ default }}",
    ]
    assert report.call_args.kwargs["reporter_tags"]["operation"] == "roadmaps.create"
    assert report.call_args.kwargs["level"] == "error"


def test_report_error_uses_exact_cleanup_group_key() -> None:
    logger = Mock()
    with (
        patch("wren_common.reporting.get_logger", return_value=logger),
        patch("wren_common.sentry.report_exception") as report,
    ):
        report_error(
            RuntimeError("cleanup failed"),
            operation="oauth.cleanup",
            domain=Domain.OAUTH,
            kind=Kind.DATABASE,
            user_id=None,
            log_event=LogEvent.UNHANDLED_EXCEPTION,
            level=ReportLevel.ERROR,
            bounded_tags={},
            context_data={},
            group_key="oauth.cleanup.database",
            group_exact=True,
        )

    assert report.call_args.kwargs["fingerprint"] == ["oauth.cleanup.database"]


def test_report_error_skips_invalid_required_group_key() -> None:
    logger = Mock()
    with (
        patch("wren_common.reporting.get_logger", return_value=logger),
        patch("wren_common.sentry.report_exception") as report,
    ):
        report_error(
            RuntimeError("boom"),
            operation="roadmaps.create",
            domain=Domain.ROADMAPS,
            kind=Kind.INTERNAL,
            user_id=None,
            log_event=LogEvent.UNHANDLED_EXCEPTION,
            level=ReportLevel.ERROR,
            bounded_tags={},
            context_data={},
            group_key="/roadmaps/{roadmap_id}",
            group_exact=True,
        )

    report.assert_not_called()
    logger.error.assert_called_once()
    logger.warning.assert_called_once_with("reporting_group_invalid", fields=["group_key"])


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


def test_contract_factory_rejects_unregistered_operation() -> None:
    with pytest.raises(ReportingContractError) as error:
        make_reporting_contract(
            operation="roadmaps.arbitrary",
            domain=Domain.ROADMAPS,
            kind=Kind.INTERNAL,
            log_event=LogEvent.UNHANDLED_EXCEPTION,
            level=ReportLevel.ERROR,
        )

    assert error.value.fields == ("operation",)


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

    assert result == {}


def test_optional_tags_omit_empty_values_and_shared_expected_marker() -> None:
    result = sanitize_tags({"component": "api", "code": "", "expected": "true", "method": "GET"})

    assert result == {"component": "api", "method": "GET"}


def test_context_rejects_request_expanded_route_identity() -> None:
    result = sanitize_context(
        {
            "path": "/roadmaps/r-123",
            "template": "/roadmaps/{roadmap_id}:validate",
            "operation": "roadmaps.get",
        }
    )

    assert result == {"template": "/roadmaps/{roadmap_id}:validate"}


def test_context_is_typed_and_records_truncation_metadata() -> None:
    original = "/" + "a" * 10_000
    unsafe_context = cast(
        "SafeContext",
        {
            "path": original,
            "status": 500,
            "query": "secret",
            "operation": {"contains": "pii"},
        },
    )
    result = sanitize_context(unsafe_context)

    assert "query" not in result
    assert "operation" not in result
    assert result["status"] == 500
    assert result[CONTEXT_TRUNCATED_KEY] is True
    assert result[CONTEXT_ORIGINAL_BYTES_KEY] == len(original.encode("utf-8"))
    assert (
        len(json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode())
        <= MAX_CONTEXT_BYTES
    )
    assert isinstance(result["path"], str)
    assert result["path"] != original


def test_context_keeps_budget_with_multiple_truncated_values() -> None:
    path = "/" + "p" * 20_000
    template = "/" + "t" * 20_000

    result = sanitize_context({"path": path, "template": template})

    assert result[CONTEXT_TRUNCATED_KEY] is True
    assert result[CONTEXT_ORIGINAL_BYTES_KEY] == len(path) + len(template)
    assert (
        len(json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode())
        <= MAX_CONTEXT_BYTES
    )


def test_contract_rejects_enum_from_the_wrong_taxonomy() -> None:
    with pytest.raises(ReportingContractError) as error:
        make_reporting_contract(
            operation="roadmaps.create",
            domain=Kind.INTERNAL,
            kind=Kind.INTERNAL,
            log_event=LogEvent.UNHANDLED_EXCEPTION,
            level=ReportLevel.ERROR,
        )

    assert error.value.fields == ("domain",)
