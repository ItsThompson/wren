"""Integration tests: the roadmaps migration and repository against real Postgres.

Applies Alembic to head on a containerized ``postgres:17-alpine`` and exercises
the SQLAlchemy repository + service end to end, so the JSONB document round-trip,
owner-scoped reads, and the global roadmap-ID existence check run against the
real asyncpg driver. Skipped automatically when Docker is unavailable.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tests.support.fakes.roadmaps_fakes import constant_follower_counter
from wren.core.db import create_database
from wren.core.errors import NotFound
from wren.roadmaps.models import RoadmapRecord
from wren.roadmaps.read_service import RoadmapReadService
from wren.roadmaps.repository import SqlAlchemyRoadmapRepository
from wren.roadmaps.schemas import (
    ChecklistItemInput,
    ResourceInput,
    ResourceType,
    RoadmapInput,
    SectionInput,
    SubsectionInput,
)
from wren.roadmaps.service import RoadmapService

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def migrated_roadmaps_url(postgres_url: str) -> Iterator[str]:
    """Apply Alembic to head against the container (sync: env.py drives asyncio)."""
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


def _doc(title: str = "Grokking DSA") -> RoadmapInput:
    return RoadmapInput(
        title=title,
        subject_tags=["cs"],
        sections=[
            SectionInput(
                title="Foundations",
                subsections=[
                    SubsectionInput(
                        proposed_id="sub_arrays",
                        title="Arrays",
                        prereq_ids=[],
                        resources=[
                            ResourceInput(
                                title="Guide", url="https://x.test", type=ResourceType.ARTICLE
                            )
                        ],
                        checklist_items=[ChecklistItemInput(text="Read it")],
                    )
                ],
            )
        ],
    )


async def test_migration_creates_the_roadmaps_table(migrated_roadmaps_url: str) -> None:
    database = create_database(migrated_roadmaps_url)
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
    assert "roadmaps" in tables


async def test_create_draft_persists_and_owner_read_round_trips(
    migrated_roadmaps_url: str,
) -> None:
    database = create_database(migrated_roadmaps_url)
    try:
        async with database.sessionmaker() as session:
            service = RoadmapService(
                SqlAlchemyRoadmapRepository(session), follower_counter=constant_follower_counter()
            )
            created = await service.create_draft("owner-1", _doc())
            roadmap_id = created.id

        # A fresh session reads the persisted JSONB document back into the model.
        async with database.sessionmaker() as session:
            read_service = RoadmapReadService(SqlAlchemyRoadmapRepository(session))
            fetched = await read_service.get("owner-1", roadmap_id)
            assert fetched.id == roadmap_id
            assert fetched.subject_tags == ["cs"]
            assert "sub_arrays" in fetched.sections["sec_foundations"].subsections

        # A non-owner read is a NotFound (owner-scoped query, no existence leak).
        async with database.sessionmaker() as session:
            read_service = RoadmapReadService(SqlAlchemyRoadmapRepository(session))
            with pytest.raises(NotFound):
                await read_service.get("intruder", roadmap_id)
    finally:
        await database.engine.dispose()


async def test_roadmap_id_existence_check_sees_persisted_rows(
    migrated_roadmaps_url: str,
) -> None:
    database = create_database(migrated_roadmaps_url)
    try:
        async with database.sessionmaker() as session:
            service = RoadmapService(
                SqlAlchemyRoadmapRepository(session), follower_counter=constant_follower_counter()
            )
            created = await service.create_draft("owner-2", _doc("Unique Title"))

        async with database.sessionmaker() as session:
            repo = SqlAlchemyRoadmapRepository(session)
            assert await repo.roadmap_id_exists(created.id) is True
            assert await repo.roadmap_id_exists("never-minted-9999") is False
    finally:
        await database.engine.dispose()


async def test_repository_rollback_after_a_duplicate_insert(migrated_roadmaps_url: str) -> None:
    # A duplicate primary key surfaces as an IntegrityError at flush; the
    # repository's rollback unwinds the failed transaction so the session stays
    # usable. (The service pre-checks IDs, so this exercises the guard directly.)
    from sqlalchemy.exc import IntegrityError

    database = create_database(migrated_roadmaps_url)
    try:
        async with database.sessionmaker() as session:
            service = RoadmapService(
                SqlAlchemyRoadmapRepository(session), follower_counter=constant_follower_counter()
            )
            created = await service.create_draft("owner-3", _doc("Collision Title"))

        async with database.sessionmaker() as session:
            repo = SqlAlchemyRoadmapRepository(session)
            existing = await repo.get_owned(created.id, "owner-3")
            assert existing is not None
            duplicate = RoadmapRecord(
                id=created.id,
                owner="owner-3",
                title="dup",
                status="draft",
                visibility="private",
                revision=1,
                document=existing.document,
                created_at=existing.created_at,
                updated_at=existing.updated_at,
            )
            with pytest.raises(IntegrityError):
                await repo.add(duplicate)
            await repo.rollback()
    finally:
        await database.engine.dispose()
