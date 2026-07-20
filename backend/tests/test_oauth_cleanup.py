"""Unit tests for the stale-client reaper wiring (:mod:`wren.oauth.cleanup`).

The loop and start/stop helpers are exercised with a fake in-memory sweep (no
DB): the reap-against-Postgres path is covered by the sweep integration test in
``test_oauth_migration`` and the ``cleanup_stale_clients`` service tests.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

from tests.oauth_fakes import build_test_codec, build_test_config, build_test_keyset
from wren.core.db import create_db_engine, create_sessionmaker
from wren.oauth.cleanup import (
    build_stale_client_sweep,
    run_cleanup_loop,
    start_stale_client_cleanup,
    stop_stale_client_cleanup,
)

if TYPE_CHECKING:
    import pytest

# Lazy engine URL: connecting is deferred, so building a session factory here
# never needs a reachable database (the reaper is only started, then cancelled).
_LAZY_URL = "postgresql+asyncpg://wren:wren@localhost:5432/wren"


def _lazy_sessionmaker() -> object:
    return create_sessionmaker(create_db_engine(_LAZY_URL))


def _config_and_codec() -> tuple[object, object]:
    config = build_test_config()
    return config, build_test_codec(config, build_test_keyset(config))


async def test_run_cleanup_loop_sweeps_each_interval() -> None:
    calls = 0
    reached = asyncio.Event()

    async def sweep() -> int:
        nonlocal calls
        calls += 1
        if calls >= 3:
            reached.set()
        return calls

    task = asyncio.create_task(run_cleanup_loop(sweep, interval=timedelta(0)))
    await asyncio.wait_for(reached.wait(), timeout=1)
    await stop_stale_client_cleanup(task)

    assert calls >= 3


async def test_run_cleanup_loop_continues_after_a_failing_sweep() -> None:
    calls = 0
    reached = asyncio.Event()

    async def sweep() -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("db unavailable")
        reached.set()
        return 0

    task = asyncio.create_task(run_cleanup_loop(sweep, interval=timedelta(0)))
    await asyncio.wait_for(reached.wait(), timeout=1)
    await stop_stale_client_cleanup(task)

    # The reaper survived the first sweep raising and swept again.
    assert calls >= 2


async def test_start_is_disabled_for_a_non_positive_interval() -> None:
    config, codec = _config_and_codec()
    task = start_stale_client_cleanup(
        _lazy_sessionmaker(),  # type: ignore[arg-type]
        config,  # type: ignore[arg-type]
        codec,  # type: ignore[arg-type]
        interval=timedelta(0),
        max_age=timedelta(days=30),
    )
    assert task is None


async def test_start_returns_a_task_that_stop_cancels() -> None:
    config, codec = _config_and_codec()
    task = start_stale_client_cleanup(
        _lazy_sessionmaker(),  # type: ignore[arg-type]
        config,  # type: ignore[arg-type]
        codec,  # type: ignore[arg-type]
        interval=timedelta(hours=6),
        max_age=timedelta(days=30),
    )
    assert task is not None
    assert not task.done()

    await stop_stale_client_cleanup(task)
    assert task.cancelled()


async def test_stop_is_a_no_op_when_the_reaper_was_disabled() -> None:
    await stop_stale_client_cleanup(None)


class _FakeSession:
    """An async-context session stand-in that records open/close."""

    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> _FakeSession:
        self.entered = True
        return self

    async def __aexit__(self, *exc: object) -> bool:
        self.exited = True
        return False


class _FakeTokenService:
    """Captures the ``older_than`` the sweep forwards; returns a fixed reap count."""

    def __init__(self) -> None:
        self.older_than: timedelta | None = None

    async def cleanup_stale_clients(self, *, older_than: timedelta) -> int:
        self.older_than = older_than
        return 7


async def test_build_stale_client_sweep_opens_a_session_and_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The DB is the external boundary: stand in a fake session + service to assert
    # the sweep opens (and closes) a session and forwards ``max_age`` to the reap.
    session = _FakeSession()
    service = _FakeTokenService()
    monkeypatch.setattr(
        "wren.oauth.cleanup.build_token_service",
        lambda _session, _config, _codec: service,
    )
    config, codec = _config_and_codec()

    sweep = build_stale_client_sweep(
        lambda: session,  # type: ignore[arg-type]
        config,  # type: ignore[arg-type]
        codec,  # type: ignore[arg-type]
        max_age=timedelta(days=1),
    )
    deleted = await sweep()

    assert deleted == 7
    assert service.older_than == timedelta(days=1)
    assert session.entered
    assert session.exited
