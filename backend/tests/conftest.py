"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from wren.core.settings import AppSettings

MakeSettings = Callable[..., AppSettings]


@pytest.fixture
def make_settings() -> MakeSettings:
    """Factory for AppSettings with sensible test defaults and per-test overrides."""

    def _make(**overrides: object) -> AppSettings:
        base: dict[str, object] = {
            "service": "wren-test",
            "port": 9999,
            "environment": "production",
            "log_level": "info",
            "host": "127.0.0.1",
            "database_url": "postgresql+asyncpg://wren:wren@localhost:5432/wren",
        }
        base.update(overrides)
        return AppSettings(**base)  # type: ignore[arg-type]

    return _make
