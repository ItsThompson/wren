"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from wren.core.settings import AppSettings

MakeSettings = Callable[..., AppSettings]


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A live ``postgres:17-alpine`` connection URL (asyncpg driver).

    Session-scoped so integration tests across files share one container. Skips
    automatically when testcontainers or Docker is unavailable, so a Docker-less
    checkout still runs the unit suite.
    """
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:  # pragma: no cover - env without testcontainers
        pytest.skip("testcontainers not installed")

    try:
        with PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres:
            yield postgres.get_connection_url()
    except Exception as exc:  # pragma: no cover - Docker daemon unavailable
        pytest.skip(f"Docker unavailable for integration tests: {exc}")


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
            "internal_api_token": "test-internal-token",
            "session_jwt_secret": "test-session-secret",
            "cookie_domain": "",
        }
        base.update(overrides)
        return AppSettings(**base)  # type: ignore[arg-type]

    return _make
