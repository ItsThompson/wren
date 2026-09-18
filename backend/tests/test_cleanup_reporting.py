"""OAuth cleanup reporting remains bounded while the loop keeps running."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

import httpx
import sqlalchemy.exc
import structlog

from wren.oauth import cleanup

if TYPE_CHECKING:
    import pytest


async def test_cleanup_uses_independent_budgets_for_failure_classes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_calls: list[BaseException] = []
    reached = asyncio.Event()
    failures = [
        sqlalchemy.exc.OperationalError("select", {}, RuntimeError("db")),
        httpx.ConnectError("upstream"),
        sqlalchemy.exc.OperationalError("select", {}, RuntimeError("db")),
        httpx.ConnectError("upstream"),
    ]
    attempt = 0

    class Limiter:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def allow(self, key: str) -> bool:
            self.calls.append(key)
            return len([call for call in self.calls if call == key]) == 1

    limiters = {key: Limiter() for key in ("internal", "database", "upstream", "timeout")}
    monkeypatch.setattr(cleanup, "_CLEANUP_REPORT_LIMITER", limiters["internal"])
    monkeypatch.setattr(cleanup, "_CLEANUP_REPORT_LIMITERS", limiters)
    monkeypatch.setattr(cleanup, "report_cleanup_failure", report_calls.append)

    async def failing_sweep() -> int:
        nonlocal attempt
        if attempt == len(failures):
            reached.set()
            return 0
        failure = failures[attempt]
        attempt += 1
        raise failure

    task = asyncio.create_task(cleanup.run_cleanup_loop(failing_sweep, interval=timedelta(0)))
    await asyncio.wait_for(reached.wait(), timeout=1)
    await cleanup.stop_stale_client_cleanup(task)

    assert len(report_calls) == 2
    assert limiters["database"].calls == ["database", "database"]
    assert limiters["upstream"].calls == ["upstream", "upstream"]


async def test_cleanup_reports_once_when_sweeps_fail_repeatedly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_calls: list[BaseException] = []
    limiter_calls: list[str] = []
    reached = asyncio.Event()
    attempts = 0

    class Limiter:
        def allow(self, key: str) -> bool:
            limiter_calls.append(key)
            return len(limiter_calls) == 1

    async def failing_sweep() -> int:
        nonlocal attempts
        attempts += 1
        if attempts >= 3:
            reached.set()
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(cleanup, "_CLEANUP_REPORT_LIMITER", Limiter())
    monkeypatch.setattr(cleanup, "report_cleanup_failure", report_calls.append)
    monkeypatch.setattr(cleanup, "_log", cleanup._log.bind(test="cleanup-reporting"))

    task = asyncio.create_task(cleanup.run_cleanup_loop(failing_sweep, interval=timedelta(0)))
    await asyncio.wait_for(reached.wait(), timeout=1)
    await cleanup.stop_stale_client_cleanup(task)

    assert attempts >= 3
    assert limiter_calls == ["oauth.cleanup"] * attempts
    assert len(report_calls) == 1
    assert isinstance(report_calls[0], RuntimeError)


async def test_cleanup_report_failure_does_not_stop_later_sweeps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_failure = RuntimeError("reporting unavailable")
    occurrence_failure = RuntimeError("database unavailable")
    reached = asyncio.Event()
    attempts = 0
    limiter_calls: list[str] = []

    class Limiter:
        def allow(self, key: str) -> bool:
            limiter_calls.append(key)
            return True

    async def sweep() -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise occurrence_failure
        reached.set()
        return 0

    def failing_report(_exception: BaseException) -> None:
        raise report_failure

    cap = structlog.testing.CapturingLogger()
    monkeypatch.setattr(cleanup, "_CLEANUP_REPORT_LIMITER", Limiter())
    monkeypatch.setattr(cleanup, "report_cleanup_failure", failing_report)
    monkeypatch.setattr(cleanup, "_log", cap)

    task = asyncio.create_task(cleanup.run_cleanup_loop(sweep, interval=timedelta(0)))
    await asyncio.wait_for(reached.wait(), timeout=1)
    await cleanup.stop_stale_client_cleanup(task)

    assert attempts >= 2
    assert limiter_calls == ["oauth.cleanup"]
    error_calls = [call for call in cap.calls if call.method_name == "error"]
    assert len(error_calls) == 1
    assert error_calls[0].args == ("oauth_client_cleanup_failed",)
    warning_calls = [call for call in cap.calls if call.method_name == "warning"]
    assert len(warning_calls) == 1
    assert warning_calls[0].args == ("oauth_client_cleanup_report_failed",)
    assert warning_calls[0].kwargs["error_kind"] == "internal"
    assert warning_calls[0].kwargs["exc_info"] is report_failure
