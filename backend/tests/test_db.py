"""Unit tests for the async DB layer (no database required).

The success paths that need a live Postgres (readiness ok, fetch_optional,
unique-violation detection against a real IntegrityError) are covered in
test_db_integration.py via testcontainers.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from wren.core.db import (
    MAX_OVERFLOW,
    POOL_SIZE,
    Database,
    create_database,
    create_db_engine,
    create_db_lifespan,
    create_sessionmaker,
    db_readiness_check,
    get_session,
    is_unique_violation,
)

# An unroutable target so connect fails fast (ECONNREFUSED on loopback).
UNREACHABLE_URL = "postgresql+asyncpg://wren:wren@127.0.0.1:1/wren"


class _DriverError(Exception):
    """Mimics an asyncpg driver error carrying a SQLSTATE."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__("driver error")
        self.sqlstate = sqlstate


class _PsycopgError(Exception):
    """Mimics a psycopg driver error carrying a pgcode."""

    def __init__(self, pgcode: str) -> None:
        super().__init__("driver error")
        self.pgcode = pgcode


class _IntegrityError(Exception):
    """Mimics SQLAlchemy's IntegrityError wrapping the driver error on .orig."""

    def __init__(self, orig: Exception) -> None:
        super().__init__("integrity error")
        self.orig = orig


def test_is_unique_violation_true_for_wrapped_sqlstate() -> None:
    exc = _IntegrityError(_DriverError("23505"))
    assert is_unique_violation(exc) is True


def test_is_unique_violation_true_for_pgcode_variant() -> None:
    exc = _IntegrityError(_PsycopgError("23505"))
    assert is_unique_violation(exc) is True


def test_is_unique_violation_false_for_other_sqlstate() -> None:
    # 23503 is a foreign-key violation, not a unique violation.
    exc = _IntegrityError(_DriverError("23503"))
    assert is_unique_violation(exc) is False


def test_is_unique_violation_false_for_unrelated_exception() -> None:
    assert is_unique_violation(ValueError("boom")) is False


def test_create_db_engine_uses_a_bounded_pool() -> None:
    engine = create_db_engine(UNREACHABLE_URL)
    assert isinstance(engine, AsyncEngine)
    assert engine.pool.size() == POOL_SIZE
    assert engine.url.drivername == "postgresql+asyncpg"
    assert POOL_SIZE > 0
    assert MAX_OVERFLOW >= 0


def test_create_database_pairs_engine_and_sessionmaker() -> None:
    database = create_database(UNREACHABLE_URL)
    assert isinstance(database, Database)
    assert isinstance(database.engine, AsyncEngine)
    assert isinstance(database.sessionmaker, async_sessionmaker)


async def test_db_readiness_check_reports_not_ok_when_unreachable() -> None:
    engine = create_db_engine(UNREACHABLE_URL)
    try:
        result = await db_readiness_check(engine)()
    finally:
        await engine.dispose()
    assert result.name == "postgres"
    assert result.ok is False
    assert result.detail  # carries the connection error


async def test_create_db_lifespan_disposes_engine_on_shutdown() -> None:
    engine = create_db_engine(UNREACHABLE_URL)
    lifespan = create_db_lifespan(engine)
    async with lifespan(FastAPI()):
        pass
    # A disposed pool is replaced; re-disposing is a safe no-op.
    await engine.dispose()


def test_get_session_yields_asyncsession_from_app_state() -> None:
    # Sociable: exercise the real FastAPI dependency wiring. Creating the session
    # does not open a connection, so no live database is needed.
    engine = create_db_engine(UNREACHABLE_URL)
    app = FastAPI(lifespan=create_db_lifespan(engine))
    app.state.db = Database(engine=engine, sessionmaker=create_sessionmaker(engine))

    @app.get("/_session_probe")
    async def probe(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
        return {"type": type(session).__name__}

    with TestClient(app) as client:
        response = client.get("/_session_probe")

    assert response.status_code == 200
    assert response.json() == {"type": "AsyncSession"}
