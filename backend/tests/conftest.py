"""Shared test fixtures."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator

import pytest

from wren.core.settings import AppSettings

MakeSettings = Callable[..., AppSettings]


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Provide a live PostgreSQL URL for integration tests.

    ``WREN_TEST_POSTGRES_URL`` supports externally managed PostgreSQL containers
    when Testcontainers cannot connect to the host Docker socket. Without it,
    the fixture uses the standard session-scoped Testcontainers path and skips
    when Docker is unavailable.
    """
    configured_url = os.getenv("WREN_TEST_POSTGRES_URL")
    if configured_url:
        yield configured_url
        return

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
            "oauth_issuer_url": "https://api.usewren.com",
            "web_app_url": "https://usewren.com",
            "mcp_resource_url": "https://mcp.usewren.com",
            "oauth_private_key_path": "",
            "oauth_key_id": "test-kid",
            "oauth_access_ttl_seconds": 900,
            "oauth_refresh_ttl_seconds": 2_592_000,
            "cors_origin": "https://usewren.com",
            "discord_webhook_url": "",
        }
        base.update(overrides)
        return AppSettings(**base)  # type: ignore[arg-type]

    return _make
