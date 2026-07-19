"""Integration tests: the DB layer and migrations against a real Postgres.

Uses testcontainers-python to run ``postgres:17-alpine`` (the pinned dev/prod
image). Skipped automatically when Docker is unavailable, so a
Docker-less checkout still runs the unit suite; CI's ``test-backend`` job has
Docker and runs these.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from wren.core.db import (
    create_db_engine,
    create_sessionmaker,
    db_readiness_check,
    fetch_optional,
    is_unique_violation,
)

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]

_metadata = sa.MetaData()
_widgets = sa.Table(
    "widgets",
    _metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String(50), nullable=False, unique=True),
)


def test_alembic_upgrade_head_creates_version_table(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # env.py reads DATABASE_URL from settings; point it at the container. This
    # test is sync because Alembic's env.py drives its own asyncio.run().
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    command.upgrade(config, "head")

    async def _read_version() -> str | None:
        engine = create_db_engine(postgres_url)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT version_num FROM alembic_version"))
                return result.scalar_one_or_none()
        finally:
            await engine.dispose()

    # Head advances as new migrations are added; onboarding is the latest.
    assert asyncio.run(_read_version()) == "0006_onboarding"


async def test_db_readiness_check_ok_against_real_db(postgres_url: str) -> None:
    engine = create_db_engine(postgres_url)
    try:
        result = await db_readiness_check(engine)()
    finally:
        await engine.dispose()
    assert result.name == "postgres"
    assert result.ok is True
    assert result.detail is None


async def test_fetch_optional_resolves_no_rows_to_none_and_returns_the_row(
    postgres_url: str,
) -> None:
    engine = create_db_engine(postgres_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_metadata.create_all)
            await conn.execute(sa.insert(_widgets).values(id=1, name="alpha"))

        async with create_sessionmaker(engine)() as session:
            present = await fetch_optional(
                session, sa.select(_widgets.c.name).where(_widgets.c.id == 1)
            )
            absent = await fetch_optional(
                session, sa.select(_widgets.c.name).where(_widgets.c.id == 999)
            )

        async with engine.begin() as conn:
            await conn.run_sync(_metadata.drop_all)
    finally:
        await engine.dispose()

    assert present == "alpha"
    assert absent is None


async def test_unique_violation_is_detected_on_duplicate_insert(postgres_url: str) -> None:
    engine = create_db_engine(postgres_url)
    caught: IntegrityError | None = None
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_metadata.create_all)

        async with create_sessionmaker(engine)() as session:
            await session.execute(sa.insert(_widgets).values(id=1, name="dup"))
            await session.commit()
            try:
                await session.execute(sa.insert(_widgets).values(id=2, name="dup"))
                await session.commit()
            except IntegrityError as exc:
                caught = exc

        async with engine.begin() as conn:
            await conn.run_sync(_metadata.drop_all)
    finally:
        await engine.dispose()

    assert caught is not None
    assert is_unique_violation(caught) is True
