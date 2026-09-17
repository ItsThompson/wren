from __future__ import annotations

from unittest.mock import Mock, patch

from wren_common import sentry
from wren_common.limiter import EventLimiter
from wren_common.reporting import ReportCategory


def setup_function() -> None:
    sentry._initialized = False
    sentry._disabled_logged = False


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


def test_initialize_sentry_is_idempotent() -> None:
    with patch("wren_common.sentry.sentry_sdk.init") as init:
        assert (
            sentry.initialize_sentry(
                dsn="https://public@example.ingest.sentry.io/1",
                environment="production",
                release="release-1",
            )
            is True
        )
        assert (
            sentry.initialize_sentry(
                dsn="https://public@example.ingest.sentry.io/1",
                environment="production",
                release="release-1",
            )
            is False
        )

    init.assert_called_once_with(
        dsn="https://public@example.ingest.sentry.io/1",
        environment="production",
        release="release-1",
        send_default_pii=False,
        before_send=sentry._scrub_event,
        integrations=[],
        traces_sample_rate=0.0,
    )


def test_initialize_sentry_prefixes_bare_deploy_sha_by_service() -> None:
    with patch("wren_common.sentry.sentry_sdk.init") as init:
        assert (
            sentry.initialize_sentry(
                dsn="https://public@example.ingest.sentry.io/1",
                environment="production",
                release="abc123",
                service="wren-mcp",
            )
            is True
        )
    assert init.call_args.kwargs["release"] == "wren-mcp@abc123"


def test_report_exception_skips_expected_category() -> None:
    with patch("wren_common.sentry.sentry_sdk.capture_exception") as capture:
        result = sentry.report_exception(ValueError("bad input"), category=ReportCategory.EXPECTED)
    assert result is None
    capture.assert_not_called()


def test_report_exception_applies_tags_context_and_limiter() -> None:
    scope = Mock()
    scope_manager = Mock()
    scope_manager.__enter__ = Mock(return_value=scope)
    scope_manager.__exit__ = Mock(return_value=None)
    limiter = EventLimiter(limit=1, window_seconds=60, clock=lambda: 0.0)

    with (
        patch("wren_common.sentry.sentry_sdk.push_scope", return_value=scope_manager),
        patch("wren_common.sentry.sentry_sdk.capture_exception", return_value="event-1") as capture,
    ):
        exception = RuntimeError("database unavailable")
        assert (
            sentry.report_exception(
                exception,
                limiter=limiter,
                tags={"service": "wren-api"},
                context={"operation": "save"},
            )
            == "event-1"
        )
        assert sentry.report_exception(exception, limiter=limiter) is None

    scope.set_tag.assert_any_call("report_category", "unexpected")
    scope.set_tag.assert_any_call("service", "wren-api")
    scope.set_context.assert_called_once_with("report", {"operation": "save"})
    capture.assert_called_once_with(exception)
