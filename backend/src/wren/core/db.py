"""Async persistence layer.

The single async SQLAlchemy engine, session factory, and the ``get_session``
FastAPI dependency every repository (Ticket 6+) depends on, plus the two boundary
helpers the service layer needs: :func:`is_unique_violation` (Postgres
unique-constraint breach -> a signal the service raises as ``Conflict``) and
:func:`fetch_optional` (no-rows fetch -> ``None``).

The pool is bounded and sized for a single backend instance (spec section 11:
~5 concurrent users, one VPS). Connecting is lazy, so building an app that wires
the engine does not require a reachable database; the ``/readyz`` check
(:func:`db_readiness_check`) is what surfaces connectivity.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from sqlalchemy import Select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from starlette.requests import Request
from starlette.types import Lifespan

from wren.core.health import CheckResult, ReadinessCheck

# Pool sized for one backend instance (spec section 11). `pool_pre_ping` discards
# connections severed by a Postgres restart or idle timeout before they are handed
# to a request.
POOL_SIZE = 5
MAX_OVERFLOW = 5
POOL_TIMEOUT_SECONDS = 30

# Postgres SQLSTATE for a unique-constraint violation (asyncpg surfaces it as
# `sqlstate`, psycopg as `pgcode`).
UNIQUE_VIOLATION_SQLSTATE = "23505"

DB_CHECK_NAME = "postgres"


def create_db_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Build the async engine backed by a bounded connection pool."""
    return create_async_engine(
        database_url,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT_SECONDS,
        pool_pre_ping=True,
        echo=echo,
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build the session factory. ``expire_on_commit=False`` keeps ORM objects
    usable after the request's commit (they are serialized post-commit)."""
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@dataclass(frozen=True)
class Database:
    """The engine + session factory pair carried on ``app.state.db``."""

    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]


def create_database(database_url: str) -> Database:
    """Compose the engine and session factory for one app."""
    engine = create_db_engine(database_url)
    return Database(engine=engine, sessionmaker=create_sessionmaker(engine))


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped :class:`AsyncSession`.

    The session factory is read from ``app.state.db`` (attached at wiring time),
    so this dependency has no module-global state and is trivially substitutable
    in tests.
    """
    database: Database = request.app.state.db
    async with database.sessionmaker() as session:
        yield session


def create_db_lifespan(engine: AsyncEngine) -> Lifespan[FastAPI]:
    """Lifespan that disposes the connection pool on shutdown."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    return lifespan


def db_readiness_check(engine: AsyncEngine) -> ReadinessCheck:
    """Readiness check that confirms Postgres is reachable.

    Plugs into the ``readiness_checks`` seam of ``create_app`` so ``GET /readyz``
    returns 503 when Postgres is unreachable. Never raises: a connectivity failure
    resolves to a failed :class:`CheckResult`.
    """

    async def check() -> CheckResult:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - any driver/connection error is "not ready"
            return CheckResult(name=DB_CHECK_NAME, ok=False, detail=str(exc))
        return CheckResult(name=DB_CHECK_NAME, ok=True)

    return check


def is_unique_violation(exc: BaseException) -> bool:
    """True if ``exc`` is (or wraps) a Postgres unique-constraint violation.

    SQLAlchemy raises ``IntegrityError`` wrapping the driver error on ``.orig``;
    the driver error carries the SQLSTATE. The service layer catches the
    ``IntegrityError`` and raises ``Conflict`` (Ticket 3) when this returns True.
    """
    driver_error = getattr(exc, "orig", exc)
    sqlstate = getattr(driver_error, "sqlstate", None) or getattr(driver_error, "pgcode", None)
    return sqlstate == UNIQUE_VIOLATION_SQLSTATE


async def fetch_optional[T](session: AsyncSession, statement: Select[tuple[T]]) -> T | None:
    """Execute a scalar-returning select and resolve a no-rows result to ``None``.

    The single canonical "one row or None" fetch every repository uses, so the
    no-rows contract is not re-decided per query.
    """
    result = await session.execute(statement)
    return result.scalar_one_or_none()
