"""OAuth cleanup reporting remains bounded while the loop keeps running."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

from wren.oauth import cleanup

if TYPE_CHECKING:
    import pytest


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
