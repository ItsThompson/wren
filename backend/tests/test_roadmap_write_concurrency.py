"""PostgreSQL locking regressions for roadmap writes."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete as sa_delete

from wren.core.db import create_db_engine, create_sessionmaker
from wren.roadmaps.models import RoadmapRecord
from wren.roadmaps.repository import SqlAlchemyRoadmapRepository, transaction
from wren.roadmaps.schemas import Roadmap, RoadmapStatus, Visibility

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROADMAP_ID = "concurrency-roadmap"
OWNER = "concurrency-owner"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> Iterator[str]:
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


async def _seed(url: str) -> None:
    engine = create_db_engine(url)
    try:
        async with create_sessionmaker(engine)() as session:
            await session.execute(sa_delete(RoadmapRecord).where(RoadmapRecord.id == ROADMAP_ID))
            session.add(
                RoadmapRecord(
                    id=ROADMAP_ID,
                    owner=OWNER,
                    title="Concurrency",
                    status=RoadmapStatus.DRAFT.value,
                    visibility=Visibility.PRIVATE.value,
                    revision=1,
                    document=Roadmap(
                        id=ROADMAP_ID,
                        owner=OWNER,
                        title="Concurrency",
                        status=RoadmapStatus.DRAFT,
                        visibility=Visibility.PRIVATE,
                        revision=1,
                        created_at=NOW,
                        updated_at=NOW,
                    ).model_dump(mode="json"),
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            await session.commit()
    finally:
        await engine.dispose()


async def test_locked_writer_waits_and_reads_committed_revision(migrated_url: str) -> None:
    await _seed(migrated_url)
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    first_locked = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()

    async def first_writer() -> None:
        async with sessionmaker() as session:
            repo = SqlAlchemyRoadmapRepository(session)
            current = await repo.get_owned_for_update(ROADMAP_ID, OWNER)
            assert current is not None
            first_locked.set()
            await release_first.wait()
            await repo.save(
                Roadmap.model_validate(current.document).model_copy(
                    update={"revision": 2, "status": RoadmapStatus.PUBLISHED}
                )
            )
            await repo.commit()

    async def second_writer() -> RoadmapRecord | None:
        async with sessionmaker() as session:
            repo = SqlAlchemyRoadmapRepository(session)
            second_started.set()
            return await repo.get_for_update(ROADMAP_ID)

    try:
        first_task = asyncio.create_task(first_writer())
        await asyncio.wait_for(first_locked.wait(), timeout=2)
        second_task = asyncio.create_task(second_writer())
        await asyncio.wait_for(second_started.wait(), timeout=2)
        await asyncio.sleep(0)
        assert not second_task.done()
        release_first.set()
        await asyncio.wait_for(first_task, timeout=2)
        current = await asyncio.wait_for(second_task, timeout=2)
        assert current is not None
        assert current.revision == 2
        assert current.status == RoadmapStatus.PUBLISHED.value
    finally:
        release_first.set()
        await engine.dispose()


async def test_lock_rolls_back_after_failed_mutation(migrated_url: str) -> None:
    await _seed(migrated_url)
    engine = create_db_engine(migrated_url)
    try:
        async with create_sessionmaker(engine)() as session:
            repo = SqlAlchemyRoadmapRepository(session)

            async def failed_mutation() -> None:
                async with transaction(repo):
                    assert await repo.get_owned_for_update(ROADMAP_ID, OWNER) is not None
                    raise RuntimeError("validation failed")

            with pytest.raises(RuntimeError):
                await failed_mutation()

        async with create_sessionmaker(engine)() as session:
            current = await SqlAlchemyRoadmapRepository(session).get_for_update(ROADMAP_ID)
            assert current is not None
            assert current.revision == 1
    finally:
        await engine.dispose()
