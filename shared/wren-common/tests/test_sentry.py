from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

import pytest

from wren_common import sentry
from wren_common.limiter import EventLimiter
from wren_common.reporting import ReportCategory


def setup_function() -> None:
    sentry._initialized = False
    sentry._disabled_logged = False
    sentry._SERVICE = None
    sentry._disabled_services.clear()


def test_initialize_sentry_skips_blank_dsn() -> None:
    logger = Mock()
    with patch("wren_common.sentry.sentry_sdk.init") as init:
        assert (
            sentry.initialize_sentry(
                dsn="  ", environment="development", release="dev", logger=logger
            )
            is False
        )
    init.assert_not_called()
    logger.info.assert_called_once_with("sentry_disabled", reason="dsn_not_configured")


def test_blank_dsn_blocks_the_sdk_capture_path() -> None:
    logger = Mock()
    with (
        patch("wren_common.sentry.sentry_sdk.new_scope") as new_scope,
        patch("wren_common.sentry.sentry_sdk.capture_exception") as capture,
    ):
        sentry.initialize_sentry(dsn="", environment="development", release="", logger=logger)
        result = sentry.report_exception(RuntimeError("boom"), limiter=None)

    assert result is None
    new_scope.assert_not_called()
    capture.assert_not_called()


def test_initialize_sentry_is_idempotent() -> None:
    release = "0123456789abcdef0123456789abcdef01234567"
    with patch("wren_common.sentry.sentry_sdk.init") as init:
        assert (
            sentry.initialize_sentry(
                dsn="https://public@example.ingest.sentry.io/1",
                environment="production",
                release=release,
            )
            is True
        )
        assert (
            sentry.initialize_sentry(
                dsn="https://public@example.ingest.sentry.io/1",
                environment="production",
                release=release,
            )
            is False
        )

    init.assert_called_once_with(
        dsn="https://public@example.ingest.sentry.io/1",
        environment="production",
        release=f"wren-api@{release}",
        send_default_pii=False,
        before_send=sentry._scrub_event,
        default_integrations=False,
        integrations=[],
        propagate_traces=False,
        traces_sample_rate=None,
        max_breadcrumbs=0,
    )


def test_initialize_sentry_prefixes_bare_deploy_sha_by_service() -> None:
    release = "0123456789abcdef0123456789abcdef01234567"
    with patch("wren_common.sentry.sentry_sdk.init") as init:
        assert (
            sentry.initialize_sentry(
                dsn="https://public@example.ingest.sentry.io/1",
                environment="production",
                release=release,
                service="wren-mcp",
            )
            is True
        )
    assert init.call_args.kwargs["release"] == f"wren-mcp@{release}"


@pytest.mark.parametrize(
    "release",
    [
        "wren-api@0123456789abcdef0123456789abcdef01234567",
        "release1",
        "z123456789abcdef0123456789abcdef01234567",
    ],
)
def test_initialize_sentry_rejects_non_bare_sha_input(release: str) -> None:
    with (
        patch("wren_common.sentry.sentry_sdk.init") as init,
        pytest.raises(ValueError, match="release must be a bare 40-character"),
    ):
        sentry.initialize_sentry(
            dsn="https://public@example.ingest.sentry.io/1",
            environment="production",
            release=release,
            service="wren-mcp",
        )

    init.assert_not_called()


def test_report_exception_skips_expected_category() -> None:
    sentry._initialized = True
    with patch("wren_common.sentry.sentry_sdk.capture_exception") as capture:
        result = sentry.report_exception(ValueError("bad input"), category=ReportCategory.EXPECTED)
    assert result is None
    capture.assert_not_called()


def test_report_exception_applies_tags_context_and_limiter() -> None:
    sentry._initialized = True
    scope = Mock()
    scope_manager = Mock()
    scope_manager.__enter__ = Mock(return_value=scope)
    scope_manager.__exit__ = Mock(return_value=None)
    limiter = EventLimiter(limit=1, window_seconds=60, clock=lambda: 0.0)

    with (
        patch("wren_common.sentry.sentry_sdk.new_scope", return_value=scope_manager),
        patch("wren_common.sentry.sentry_sdk.capture_exception", return_value="event-1") as capture,
    ):
        exception = RuntimeError("database unavailable")
        assert (
            sentry.report_exception(
                exception,
                limiter=limiter,
                tags={"component": "writer"},
                context={"operation": "save"},
                user_id="user-1",
            )
            == "event-1"
        )
        assert sentry.report_exception(exception, limiter=limiter) is None

    scope.clear.assert_called_once_with()
    scope.set_tag.assert_any_call("_wren_report", "1")
    scope.set_tag.assert_any_call("report_category", "unexpected")
    scope.set_tag.assert_any_call("component", "writer")
    scope.set_tag.assert_any_call("error_kind", "internal")
    scope.set_context.assert_not_called()
    scope.set_user.assert_called_once_with({"id": "user-1"})
    capture.assert_called_once_with(exception)


def test_report_exception_rejects_unknown_taxonomy_values() -> None:
    sentry._initialized = True
    with patch("wren_common.sentry.sentry_sdk.capture_exception") as capture:
        assert (
            sentry.report_exception(RuntimeError("boom"), limiter=None, error_kind="custom") is None
        )
        assert (
            sentry.report_exception(RuntimeError("boom"), limiter=None, category="custom") is None
        )

    capture.assert_not_called()


def test_report_exception_preserves_reporter_tags_and_scope_level() -> None:
    sentry._initialized = True
    scope = Mock()
    scope_manager = Mock()
    scope_manager.__enter__ = Mock(return_value=scope)
    scope_manager.__exit__ = Mock(return_value=None)

    with (
        patch("wren_common.sentry.sentry_sdk.new_scope", return_value=scope_manager),
        patch("wren_common.sentry.sentry_sdk.capture_exception", return_value="event-1"),
    ):
        result = sentry.report_exception(
            RuntimeError("database unavailable"),
            limiter=None,
            tags={"component": "writer", "operation": "caller-value"},
            reporter_tags={
                "operation": "roadmaps.create",
                "domain": "roadmaps",
                "kind": "database",
                "log_event": "unhandled_exception",
                "level": "warning",
            },
            level="warning",
            error_kind="database",
        )

    assert result == "event-1"
    for key, value in {
        "operation": "roadmaps.create",
        "domain": "roadmaps",
        "kind": "database",
        "log_event": "unhandled_exception",
        "level": "warning",
    }.items():
        scope.set_tag.assert_any_call(key, value)
    scope.set_tag.assert_any_call("component", "writer")
    scope.set_level.assert_called_once_with("warning")


def test_scrub_event_drops_metadata_without_the_reporter_marker() -> None:
    event: Any = {
        "contexts": {"report": {"secret": "QUERY_TOKEN", "method": "GET"}},
        "tags": {"component": "HEADER_TOKEN", "unsafe": "BODY_TOKEN"},
        "user": {"id": "COOKIE_TOKEN", "email": "person@example.test"},
    }

    result = sentry._scrub_event(event, {})

    assert result["contexts"] == {}
    assert result["tags"] == {}
    assert "user" not in result


def test_scrub_event_closes_reporter_owned_metadata() -> None:
    event: Any = {
        "contexts": {
            "report": {
                "method": "GET",
                "status": 502,
                "secret": "QUERY_TOKEN",
                "nested": {"body": "BODY_TOKEN"},
            },
            "response": {"body": "BODY_TOKEN"},
        },
        "tags": {
            "_wren_report": "1",
            "_wren_tag_keys": (
                "component,operation,domain,kind,log_event,level,report_category,error_kind,service"
            ),
            "_wren_context": "1",
            "_wren_user": "1",
            "component": "api",
            "operation": "roadmaps.get",
            "domain": "roadmaps",
            "kind": "upstream",
            "log_event": "unhandled_exception",
            "level": "error",
            "report_category": "unexpected",
            "error_kind": "upstream",
            "service": "wren-external",
            "unsafe": "HEADER_TOKEN",
        },
        "user": {"id": "user-1", "email": "person@example.test"},
    }

    result = sentry._scrub_event(event, {})

    assert result["contexts"] == {"report": {"method": "GET", "status": 502}}
    assert result["tags"] == {
        "component": "api",
        "operation": "roadmaps.get",
        "domain": "roadmaps",
        "kind": "upstream",
        "log_event": "unhandled_exception",
        "level": "error",
        "report_category": "unexpected",
        "error_kind": "upstream",
        "service": "wren-external",
    }
    assert result["user"] == {"id": "user-1"}


def test_report_exception_uses_explicit_bounded_error_kind() -> None:
    sentry._initialized = True
    scope = Mock()
    scope_manager = Mock()
    scope_manager.__enter__ = Mock(return_value=scope)
    scope_manager.__exit__ = Mock(return_value=None)

    with (
        patch("wren_common.sentry.sentry_sdk.new_scope", return_value=scope_manager),
        patch("wren_common.sentry.sentry_sdk.capture_exception", return_value="event-1"),
    ):
        result = sentry.report_exception(
            RuntimeError("database unavailable"),
            limiter=None,
            tags={"error_kind": "timeout"},
            error_kind="database",
        )

    assert result == "event-1"
    scope.set_tag.assert_any_call("error_kind", "database")
    assert not any(call.args == ("error_kind", "timeout") for call in scope.set_tag.call_args_list)
