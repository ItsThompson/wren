"""Domain/service/DB-pool metrics: failure counting, combined exposure, pool events.

Covers the cross-cutting instrumentation added in Ticket 31: the
``track_failures`` service decorator, the ``/metrics`` endpoint serving the shared
custom-metrics registry alongside each app's private HTTP registry, and the
SQLAlchemy pool events wired in :mod:`wren.core.db`.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from wren.core.app_factory import create_app
from wren.core.db import _query_name, instrument_pool
from wren.core.errors import NotFound
from wren.core.observability import (
    WREN_REGISTRY,
    track_failures,
)
from wren.core.settings import AppSettings

MakeSettings = Callable[..., AppSettings]


# --- track_failures ---------------------------------------------------------


@track_failures("sample")
class _Sample:
    """A stand-in service exercising the decorator's public/private + error rules."""

    async def succeeds(self) -> str:
        return "ok"

    async def raises_domain(self) -> None:
        raise NotFound("not here")

    async def raises_unexpected(self) -> None:
        raise RuntimeError("boom")

    async def _private_unexpected(self) -> None:  # not wrapped: underscore-prefixed
        raise RuntimeError("boom")


def _failures(method: str) -> float:
    value = WREN_REGISTRY.get_sample_value(
        "service_method_failures_total", {"service": "sample", "method": method}
    )
    return value or 0.0


async def test_unexpected_error_increments_the_failure_counter() -> None:
    before = _failures("raises_unexpected")
    with pytest.raises(RuntimeError):
        await _Sample().raises_unexpected()
    assert _failures("raises_unexpected") == before + 1


async def test_wren_error_is_not_counted_as_a_failure() -> None:
    before = _failures("raises_domain")
    with pytest.raises(NotFound):
        await _Sample().raises_domain()
    # A model-recoverable 4xx domain error is an expected outcome, not a failure.
    assert _failures("raises_domain") == before


async def test_success_is_transparent_and_uncounted() -> None:
    before = _failures("succeeds")
    assert await _Sample().succeeds() == "ok"
    assert _failures("succeeds") == before


def test_decorator_preserves_public_method_identity() -> None:
    # functools.wraps keeps the name so downstream introspection is unchanged.
    assert _Sample.succeeds.__name__ == "succeeds"


async def test_private_methods_are_left_unwrapped() -> None:
    before = _failures("_private_unexpected")
    with pytest.raises(RuntimeError):
        await _Sample()._private_unexpected()
    assert _failures("_private_unexpected") == before


# --- combined /metrics exposure ---------------------------------------------


def test_metrics_endpoint_serves_http_and_custom_families(make_settings: MakeSettings) -> None:
    client = TestClient(create_app(make_settings()))
    client.get("/healthz")  # generate one HTTP sample

    body = client.get("/metrics").text
    # HTTP families from the app's private registry...
    assert "http_requests_total" in body
    # ...plus the shared custom families defined on WREN_REGISTRY.
    assert "service_method_failures_total" in body
    assert "oauth_tokens_issued_total" in body
    assert "db_query_duration_seconds" in body
    assert "active_connections" in body


# --- DB pool instrumentation -------------------------------------------------


def _query_count(query_name: str) -> float:
    value = WREN_REGISTRY.get_sample_value(
        "db_query_duration_seconds_count", {"query_name": query_name}
    )
    return value or 0.0


def _make_instrumented_sqlite() -> Engine:
    """A real in-memory SQLite engine with the pool events attached.

    ``instrument_pool`` only touches ``engine.sync_engine``; a lightweight stand-in
    carrying the real sync engine there lets the pool/cursor events fire on genuine
    query execution without needing an async driver.
    """
    sync_engine = create_engine("sqlite://")
    instrument_pool(SimpleNamespace(sync_engine=sync_engine))  # type: ignore[arg-type]
    return sync_engine


def test_query_execution_records_duration_by_verb() -> None:
    engine = _make_instrumented_sqlite()
    before = _query_count("select")
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    assert _query_count("select") == before + 1


def _active_connections() -> float:
    value = WREN_REGISTRY.get_sample_value("active_connections")
    return value or 0.0


def test_active_connections_returns_to_baseline_after_checkin() -> None:
    engine = _make_instrumented_sqlite()
    baseline = _active_connections()
    with engine.connect() as conn:
        # Checked out: the gauge reflects the live connection.
        assert _active_connections() == baseline + 1
        conn.execute(text("SELECT 1"))
    # Checked back in: the gauge is restored.
    assert _active_connections() == baseline


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("SELECT 1", "select"),
        ("  insert into t values (1)", "insert"),
        ("UPDATE t SET x = 1", "update"),
        ("delete from t", "delete"),
        ("WITH cte AS (SELECT 1) SELECT * FROM cte", "other"),
        ("", "other"),
    ],
)
def test_query_name_collapses_to_a_bounded_verb(statement: str, expected: str) -> None:
    assert _query_name(statement, {}) == expected


def test_query_name_honors_an_explicit_execution_option() -> None:
    assert _query_name("SELECT 1", {"query_name": "readiness_probe"}) == "readiness_probe"
