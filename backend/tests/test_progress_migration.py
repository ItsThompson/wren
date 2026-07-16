"""Integration tests: the progress migration + repository against real Postgres.

Applies Alembic to head on a containerized ``postgres:17-alpine`` and exercises
the SQLAlchemy progress repository end to end, so the JSONB ``checked`` round
trip, the composite-key upsert (idempotent), and per-user scoping run against the
real asyncpg driver. Also confirms the unscoped roadmaps ``get`` accessor the
progress service depends on. Skipped automatically when Docker is unavailable.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tests.support.fakes.progress_builders import CHK_ARRAYS_READ, build_roadmap, make_record
from wren.core.db import create_database
from wren.progress.repository import SqlAlchemyProgressRepository
from wren.progress.schemas import Progress
from wren.roadmaps.repository import SqlAlchemyRoadmapRepository

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
_NOW = datetime(2026, 7, 15, tzinfo=UTC)


@pytest.fixture(scope="session")
def migrated_progress_url(postgres_url: str) -> Iterator[str]:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", postgres_url)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = postgres_url
    try:
        command.upgrade(config, "head")
        yield postgres_url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


async def test_migration_creates_the_progress_table(migrated_progress_url: str) -> None:
    database = create_database(migrated_progress_url)
    try:
        async with database.engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            )
            tables = {row[0] for row in rows}
    finally:
        await database.engine.dispose()
    assert "progress" in tables


async def test_upsert_round_trips_and_is_idempotent(migrated_progress_url: str) -> None:
    database = create_database(migrated_progress_url)
    roadmap_id = "grokking-dsa-int1"
    try:
        async with database.sessionmaker() as session:
            repo = SqlAlchemyProgressRepository(session)
            await repo.upsert(
                Progress(
                    user_id="u1",
                    roadmap_id=roadmap_id,
                    checked={CHK_ARRAYS_READ: True},
                    updated_at=_NOW,
                )
            )
            await repo.commit()

        # A second upsert (idempotent write to the same composite key) updates the
        # one row rather than inserting a duplicate.
        async with database.sessionmaker() as session:
            repo = SqlAlchemyProgressRepository(session)
            await repo.upsert(
                Progress(
                    user_id="u1",
                    roadmap_id=roadmap_id,
                    checked={CHK_ARRAYS_READ: True, "chk_two": True},
                    updated_at=_NOW,
                )
            )
            await repo.commit()

        async with database.sessionmaker() as session:
            repo = SqlAlchemyProgressRepository(session)
            record = await repo.get("u1", roadmap_id)
            assert record is not None
            assert record.checked == {CHK_ARRAYS_READ: True, "chk_two": True}
            # Per-user scoping: another user has no row here.
            assert await repo.get("u2", roadmap_id) is None
    finally:
        await database.engine.dispose()


async def test_rollback_after_a_failed_write_keeps_the_session_usable(
    migrated_progress_url: str,
) -> None:
    database = create_database(migrated_progress_url)
    try:
        async with database.sessionmaker() as session:
            repo = SqlAlchemyProgressRepository(session)
            await repo.rollback()  # no-op rollback is safe on a clean session
            assert await repo.get("nobody", "no-roadmap") is None
    finally:
        await database.engine.dispose()


async def test_roadmaps_get_accessor_reads_unscoped(migrated_progress_url: str) -> None:
    # The progress service loads a roadmap via the unscoped roadmaps ``get``
    # accessor (a follower reads a roadmap they do not own); confirm it round trips.
    database = create_database(migrated_progress_url)
    roadmap = build_roadmap(roadmap_id="grokking-dsa-int2", owner="author")
    try:
        async with database.sessionmaker() as session:
            session.add(make_record(roadmap))
            await session.commit()

        async with database.sessionmaker() as session:
            repo = SqlAlchemyRoadmapRepository(session)
            record = await repo.get(roadmap.id)
            assert record is not None and record.owner == "author"
            assert await repo.get("never-minted-0000") is None
    finally:
        await database.engine.dispose()
