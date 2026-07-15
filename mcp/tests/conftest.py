"""Shared MCP test fixtures."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from token_factory import ISSUER, RESOURCE
from wren_mcp.settings import SERVICE, RsSettings

MakeSettings = Callable[..., RsSettings]


@pytest.fixture
def make_settings() -> MakeSettings:
    """Factory for RsSettings with production-like defaults and per-test overrides."""

    def _make(**overrides: object) -> RsSettings:
        base: dict[str, object] = {
            "service": SERVICE,
            "environment": "production",
            "log_level": "critical",
            "host": "127.0.0.1",
            "port": 9000,
            "issuer": ISSUER,
            "resource": RESOURCE,
            "backend_internal_url": "http://backend:8001",
            "internal_api_token": "test-internal-token",
        }
        base.update(overrides)
        return RsSettings(**base)  # type: ignore[arg-type]

    return _make
