"""DiscordRegistrationNotifier: schedule-and-return, error isolation, log-safety.

The one genuinely tricky unit in the signup-notification feature (multiple
failure modes + a security-sensitive logging path), driven out at Level 3. The
real POST path is exercised through ``httpx.MockTransport`` (no live network);
each test drains in-flight deliveries via the public ``aclose()`` seam before
asserting. Logs are asserted by resetting the module ``_log`` to a fresh
``structlog.get_logger()`` inside a ``capture_logs`` block (module loggers freeze
their processor chain at import), matching the correlation/identity tests.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import httpx
import pytest
import structlog
from pydantic import SecretStr
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars
from structlog.testing import capture_logs

from wren.accounts.notifications import (
    DiscordRegistrationNotifier,
    NullRegistrationNotifier,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, MutableMapping

    LogRecord = MutableMapping[str, object]

# A realistic-looking webhook so the leak assertions are meaningful: the secret
# token segment must never surface in any log record.
_WEBHOOK = "https://discord.com/api/webhooks/123456789012345678/secret-token-abcdefXYZ"
_WEBHOOK_SECRET = SecretStr(_WEBHOOK)


@pytest.fixture(autouse=True)
def _isolate_contextvars() -> Iterator[None]:
    """Keep one test's bound request_id from leaking into another's log record."""
    clear_contextvars()
    yield
    clear_contextvars()


def _responding_transport(
    status: int,
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    """A MockTransport that records each request and replies with ``status``."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status)

    return httpx.MockTransport(handler), seen


def _raising_transport(exc: Exception) -> httpx.MockTransport:
    """A MockTransport whose every request raises ``exc`` (unreachable/timeout)."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.MockTransport(handler)


def _notifier(transport: httpx.MockTransport) -> DiscordRegistrationNotifier:
    return DiscordRegistrationNotifier(_WEBHOOK_SECRET, transport=transport)


async def test_posts_the_username_as_discord_content() -> None:
    transport, seen = _responding_transport(204)
    notifier = _notifier(transport)

    notifier.user_registered(username="ada", user_id="user-1")
    await notifier.aclose()

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == _WEBHOOK
    assert json.loads(request.content) == {"content": "🎉 New user registered: ada"}


async def test_204_response_logs_no_failure_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    transport, _ = _responding_transport(204)
    notifier = _notifier(transport)

    with capture_logs(processors=[merge_contextvars]) as logs:
        monkeypatch.setattr("wren.accounts.notifications._log", structlog.get_logger())
        notifier.user_registered(username="ada", user_id="user-1")
        await notifier.aclose()

    assert not _failures(logs)


@pytest.mark.parametrize(
    ("exc", "expected_type"),
    [
        (httpx.ConnectError("unreachable"), "ConnectError"),
        (httpx.ReadTimeout("timed out"), "ReadTimeout"),
    ],
)
async def test_transport_errors_are_swallowed_and_logged_without_the_url(
    monkeypatch: pytest.MonkeyPatch, exc: Exception, expected_type: str
) -> None:
    notifier = _notifier(_raising_transport(exc))

    with capture_logs(processors=[merge_contextvars]) as logs:
        monkeypatch.setattr("wren.accounts.notifications._log", structlog.get_logger())
        # Neither scheduling nor draining may raise: the delivery error is
        # isolated inside the background task.
        notifier.user_registered(username="ada", user_id="user-1")
        await notifier.aclose()

    failures = _failures(logs)
    assert len(failures) == 1
    record = failures[0]
    assert record["error_type"] == expected_type
    assert record["status"] is None
    _assert_log_safe(record)


@pytest.mark.parametrize("status", [429, 500])
async def test_error_status_is_swallowed_and_logged_with_the_status(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    transport, _ = _responding_transport(status)
    notifier = _notifier(transport)

    with capture_logs(processors=[merge_contextvars]) as logs:
        monkeypatch.setattr("wren.accounts.notifications._log", structlog.get_logger())
        notifier.user_registered(username="ada", user_id="user-1")
        await notifier.aclose()

    failures = _failures(logs)
    assert len(failures) == 1
    record = failures[0]
    # raise_for_status turns a 4xx/5xx into an HTTPStatusError carrying the code.
    assert record["error_type"] == "HTTPStatusError"
    assert record["status"] == status
    _assert_log_safe(record)


async def test_the_failure_record_carries_the_correlation_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # asyncio.create_task copies the current context, so the request_id bound on
    # the handler is inherited by the delivery task's log line.
    notifier = _notifier(_raising_transport(httpx.ConnectError("unreachable")))

    with capture_logs(processors=[merge_contextvars]) as logs:
        monkeypatch.setattr("wren.accounts.notifications._log", structlog.get_logger())
        bind_contextvars(request_id="corr-signup-1")
        notifier.user_registered(username="ada", user_id="user-1")
        await notifier.aclose()

    assert _failures(logs)[0]["request_id"] == "corr-signup-1"


async def test_aclose_awaits_delivery_completion() -> None:
    # The observable contract of the drain seam: after aclose the POST has
    # actually happened (the task is not abandoned mid-flight).
    transport, seen = _responding_transport(204)
    notifier = _notifier(transport)

    notifier.user_registered(username="ada", user_id="user-1")
    await notifier.aclose()

    assert len(seen) == 1
    # A second drain with nothing pending is a no-op and does not hang.
    await notifier.aclose()
    assert len(seen) == 1


async def test_null_notifier_schedules_no_task_and_does_no_io() -> None:
    notifier = NullRegistrationNotifier()

    before = len(asyncio.all_tasks())
    notifier.user_registered(username="ada", user_id="user-1")
    # No background task was scheduled (nothing to deliver, no I/O).
    assert len(asyncio.all_tasks()) == before
    # aclose is a no-op that completes immediately.
    await notifier.aclose()


def _failures(logs: list[LogRecord]) -> list[LogRecord]:
    return [entry for entry in logs if entry.get("event") == "discord_notify_failed"]


def _assert_log_safe(record: LogRecord) -> None:
    """No webhook URL, exception object, or exc_info anywhere in the record."""
    assert "exc_info" not in record
    assert "exception" not in record
    rendered = json.dumps(record, default=repr)
    assert _WEBHOOK not in rendered
    assert "secret-token" not in rendered
    assert "discord.com" not in rendered
