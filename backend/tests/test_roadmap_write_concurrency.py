"""PostgreSQL locking regressions for roadmap writes."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete as sa_delete
from sqlalchemy import text

from wren.core.db import create_db_engine, create_sessionmaker
from wren.core.errors import Conflict, ErrorCode, NotFound
from wren.progress.repository import SqlAlchemyProgressRepository
from wren.progress.schemas import CompletionState, Progress
from wren.progress.service import ProgressService
from wren.roadmaps.models import RoadmapRecord
from wren.roadmaps.repository import SqlAlchemyRoadmapRepository, transaction
from wren.roadmaps.schemas import (
    ChecklistItemInput,
    PatchOp,
    PatchResult,
    PublishedVisibility,
    ResourceInput,
    ResourceType,
    Roadmap,
    RoadmapInput,
    RoadmapStatus,
    SectionInput,
    SetTagsOp,
    SubsectionInput,
)
from wren.roadmaps.service import RoadmapService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Coroutine, Iterator

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROADMAP_ID = "concurrency-roadmap"
OWNER = "concurrency-owner"
NOW = datetime(2026, 1, 1, tzinfo=UTC)
WRITE_TIMEOUT_SECONDS = 5


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
                    published_visibility=PublishedVisibility.PRIVATE.value,
                    revision=1,
                    document=Roadmap(
                        id=ROADMAP_ID,
                        owner=OWNER,
                        title="Concurrency",
                        status=RoadmapStatus.DRAFT,
                        published_visibility=PublishedVisibility.PRIVATE,
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


def _roadmap_input(title: str) -> RoadmapInput:
    return RoadmapInput(
        title=title,
        sections=[
            SectionInput(
                title="Core",
                subsections=[
                    SubsectionInput(
                        proposed_id="sub_core",
                        title="Core concept",
                        resources=[
                            ResourceInput(
                                title="Guide",
                                url="https://example.test/guide",
                                type=ResourceType.ARTICLE,
                            )
                        ],
                        checklist_items=[ChecklistItemInput(text="Read the guide")],
                    )
                ],
            )
        ],
        suggested_path=["sub_core"],
    )


@asynccontextmanager
async def _service_pair(
    url: str,
) -> AsyncIterator[tuple[list[RoadmapService], list[ProgressService], list[AsyncSession]]]:
    engine = create_db_engine(url)
    sessionmaker = create_sessionmaker(engine)
    sessions = [sessionmaker(), sessionmaker()]
    roadmap_repositories = [SqlAlchemyRoadmapRepository(session) for session in sessions]
    progress_repositories = [SqlAlchemyProgressRepository(session) for session in sessions]
    roadmap_services = [
        RoadmapService(
            roadmap_repository,
            follower_counter=progress_repository.count_followers,
            token_factory=lambda: "race",
            clock=lambda: NOW,
        )
        for roadmap_repository, progress_repository in zip(
            roadmap_repositories, progress_repositories, strict=True
        )
    ]
    progress_services = [
        ProgressService(roadmap_repository, progress_repository, clock=lambda: NOW)
        for roadmap_repository, progress_repository in zip(
            roadmap_repositories, progress_repositories, strict=True
        )
    ]
    try:
        yield roadmap_services, progress_services, sessions
    finally:
        for session in sessions:
            await session.close()
        await engine.dispose()


async def _read_roadmap(url: str, roadmap_id: str) -> Roadmap:
    engine = create_db_engine(url)
    try:
        async with create_sessionmaker(engine)() as session:
            record = await SqlAlchemyRoadmapRepository(session).get(roadmap_id)
            assert record is not None
            return Roadmap.model_validate(record.document)
    finally:
        await engine.dispose()


@asynccontextmanager
async def _waiting_write[Result](
    url: str,
    roadmap_id: str,
    holder: AsyncSession,
    waiter: AsyncSession,
    write: Callable[[], Coroutine[object, object, Result]],
) -> AsyncIterator[asyncio.Task[Result]]:
    # Pre-acquire the first writer's lock on the same session its service uses.
    assert await SqlAlchemyRoadmapRepository(holder).get_for_update(roadmap_id) is not None
    backend_pid = (await waiter.execute(text("SELECT pg_backend_pid()"))).scalar_one()
    task = asyncio.create_task(write())
    try:
        await asyncio.wait_for(_wait_for_lock_wait(url, backend_pid), timeout=WRITE_TIMEOUT_SECONDS)
        assert not task.done()
        yield task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await holder.rollback()


async def test_delete_and_first_follow_are_serialized_at_service_boundary(
    migrated_url: str,
) -> None:
    async with _service_pair(migrated_url) as (roadmaps, progress, _):
        created = await roadmaps[0].create_draft("owner", _roadmap_input("Delete follow race"))
        await roadmaps[0].publish("owner", created.id)
        await roadmaps[0].set_published_visibility("owner", created.id, PublishedVisibility.PUBLIC)
        delete_result, follow_result = await asyncio.gather(
            roadmaps[0].delete("owner", created.id),
            progress[1].follow("follower", created.id),
            return_exceptions=True,
        )
        if delete_result is None:
            assert isinstance(follow_result, NotFound)
        else:
            assert isinstance(delete_result, Conflict)
            assert delete_result.code is ErrorCode.DELETE_HAS_FOLLOWERS
            assert isinstance(follow_result, Progress)


async def test_archive_before_first_follow_rejects_the_waiting_follower(
    migrated_url: str,
) -> None:
    async with _service_pair(migrated_url) as (roadmaps, progress, sessions):
        created = await roadmaps[0].create_draft("owner", _roadmap_input("Archive before follow"))
        await roadmaps[0].publish("owner", created.id)
        await roadmaps[0].set_published_visibility("owner", created.id, PublishedVisibility.PUBLIC)
        async with _waiting_write(
            migrated_url,
            created.id,
            sessions[0],
            sessions[1],
            lambda: progress[1].follow("follower", created.id),
        ) as follow_task:
            archived = await roadmaps[0].archive("owner", created.id)
            assert archived.status is RoadmapStatus.ARCHIVED
            with pytest.raises(Conflict, match="only a published roadmap"):
                await asyncio.wait_for(follow_task, timeout=WRITE_TIMEOUT_SECONDS)

        assert (await _read_roadmap(migrated_url, created.id)).status is RoadmapStatus.ARCHIVED
        assert await SqlAlchemyProgressRepository(sessions[0]).get("follower", created.id) is None


async def test_first_follow_before_archive_preserves_the_existing_follower(
    migrated_url: str,
) -> None:
    async with _service_pair(migrated_url) as (roadmaps, progress, sessions):
        created = await roadmaps[0].create_draft("owner", _roadmap_input("Follow before archive"))
        await roadmaps[0].publish("owner", created.id)
        await roadmaps[0].set_published_visibility("owner", created.id, PublishedVisibility.PUBLIC)
        async with _waiting_write(
            migrated_url,
            created.id,
            sessions[0],
            sessions[1],
            lambda: roadmaps[1].archive("owner", created.id),
        ) as archive_task:
            followed = await progress[0].follow("follower", created.id)
            assert followed.user_id == "follower"
            assert followed.roadmap_id == created.id
            archived = await asyncio.wait_for(archive_task, timeout=WRITE_TIMEOUT_SECONDS)
            assert archived.status is RoadmapStatus.ARCHIVED

        assert (await _read_roadmap(migrated_url, created.id)).status is RoadmapStatus.ARCHIVED
        snapshot = await progress[0].get("follower", created.id, detailed=True)
        assert snapshot.roadmap_id == created.id
        assert snapshot.checked_ids == []


async def test_same_revision_patch_writers_have_one_winner(
    migrated_url: str,
) -> None:
    async with _service_pair(migrated_url) as (roadmaps, _, _):
        created = await roadmaps[0].create_draft("owner", _roadmap_input("Patch race"))
        operations: list[PatchOp] = [
            SetTagsOp(op="set_tags", subsection_id="sub_core", tags=["race"])
        ]
        first, second = await asyncio.gather(
            roadmaps[0].patch_draft("owner", created.id, created.revision, operations),
            roadmaps[1].patch_draft("owner", created.id, created.revision, operations),
            return_exceptions=True,
        )
        results = [first, second]
        assert sum(isinstance(result, Conflict) for result in results) == 1
        assert sum(not isinstance(result, Exception) for result in results) == 1
        assert (await _read_roadmap(migrated_url, created.id)).revision == 2


async def test_patch_and_publish_race_preserves_immutability(
    migrated_url: str,
) -> None:
    async with _service_pair(migrated_url) as (roadmaps, _, _):
        created = await roadmaps[0].create_draft("owner", _roadmap_input("Patch publish race"))
        operations: list[PatchOp] = [
            SetTagsOp(op="set_tags", subsection_id="sub_core", tags=["race"])
        ]
        patch_result, publish_result = await asyncio.gather(
            roadmaps[0].patch_draft("owner", created.id, created.revision, operations),
            roadmaps[1].publish("owner", created.id),
            return_exceptions=True,
        )
        assert (await _read_roadmap(migrated_url, created.id)).status is RoadmapStatus.PUBLISHED
        assert isinstance(publish_result, Roadmap)
        assert isinstance(patch_result, (Conflict, PatchResult))


@pytest.mark.parametrize("archive_first", [False, True], ids=["metadata-first", "archive-first"])
async def test_metadata_and_archive_preserve_both_writes_in_each_lock_order(
    migrated_url: str, archive_first: bool
) -> None:
    async with _service_pair(migrated_url) as (roadmaps, _, sessions):
        created = await roadmaps[0].create_draft(
            "owner", _roadmap_input(f"Metadata archive order {archive_first}")
        )
        await roadmaps[0].publish("owner", created.id)
        if archive_first:
            async with _waiting_write(
                migrated_url,
                created.id,
                sessions[0],
                sessions[1],
                lambda: roadmaps[1].edit_metadata("owner", created.id, "Renamed", None, None),
            ) as metadata_task:
                archive_result = await roadmaps[0].archive("owner", created.id)
                metadata_result = await asyncio.wait_for(
                    metadata_task, timeout=WRITE_TIMEOUT_SECONDS
                )
            assert metadata_result.status is RoadmapStatus.ARCHIVED
        else:
            async with _waiting_write(
                migrated_url,
                created.id,
                sessions[0],
                sessions[1],
                lambda: roadmaps[1].archive("owner", created.id),
            ) as archive_task:
                metadata_result = await roadmaps[0].edit_metadata(
                    "owner", created.id, "Renamed", None, None
                )
                archive_result = await asyncio.wait_for(archive_task, timeout=WRITE_TIMEOUT_SECONDS)
            assert metadata_result.status is RoadmapStatus.PUBLISHED
        assert metadata_result.title == "Renamed"
        assert archive_result.status is RoadmapStatus.ARCHIVED
        stored = await _read_roadmap(migrated_url, created.id)
        assert stored.status is RoadmapStatus.ARCHIVED
        assert stored.title == "Renamed"


async def test_visibility_and_patch_race_preserves_each_write(
    migrated_url: str,
) -> None:
    async with _service_pair(migrated_url) as (roadmaps, _, _):
        created = await roadmaps[0].create_draft(
            "owner", _roadmap_input("PublishedVisibility patch race")
        )
        visibility_result, patch_result = await asyncio.gather(
            roadmaps[0].set_published_visibility("owner", created.id, PublishedVisibility.PUBLIC),
            roadmaps[1].patch_draft(
                "owner",
                created.id,
                created.revision,
                [SetTagsOp(op="set_tags", subsection_id="sub_core", tags=["race"])],
            ),
        )
        assert visibility_result.published_visibility is PublishedVisibility.PUBLIC
        assert not isinstance(patch_result, Exception)
        stored = await _read_roadmap(migrated_url, created.id)
        assert stored.published_visibility is PublishedVisibility.PUBLIC
        assert stored.revision == 2


async def test_progress_and_deadline_race_preserves_unrelated_state(
    migrated_url: str,
) -> None:
    async with _service_pair(migrated_url) as (roadmaps, progress, _):
        created = await roadmaps[0].create_draft("owner", _roadmap_input("Progress deadline race"))
        await roadmaps[0].publish("owner", created.id)
        await roadmaps[0].set_published_visibility("owner", created.id, PublishedVisibility.PUBLIC)
        update_result, deadline_result = await asyncio.gather(
            progress[0].update(
                "reader", created.id, ["chk_read-the-guide"], CompletionState.COMPLETE
            ),
            progress[1].set_deadline("reader", created.id, date(2026, 12, 31)),
        )
        update_checked_ids = update_result.progress.checked_ids
        assert update_checked_ids is not None
        assert "chk_read-the-guide" in update_checked_ids
        assert deadline_result.deadline == date(2026, 12, 31)
        snapshot = await progress[0].get("reader", created.id, detailed=True)
        snapshot_checked_ids = snapshot.checked_ids
        assert snapshot_checked_ids is not None
        assert "chk_read-the-guide" in snapshot_checked_ids
        assert snapshot.deadline == date(2026, 12, 31)


async def _wait_for_lock_wait(url: str, backend_pid: int) -> None:
    engine = create_db_engine(url)
    try:
        async with create_sessionmaker(engine)() as session:
            for _ in range(200):
                result = await session.execute(
                    text(
                        """
                        SELECT wait_event_type
                        FROM pg_stat_activity
                        WHERE pid = :backend_pid
                        """
                    ),
                    {"backend_pid": backend_pid},
                )
                if result.scalar_one_or_none() == "Lock":
                    return
                await asyncio.sleep(0.01)
    finally:
        await engine.dispose()
    raise AssertionError("PostgreSQL did not report the writer waiting on a row lock")


async def test_locked_writer_waits_and_reads_committed_revision(migrated_url: str) -> None:
    await _seed(migrated_url)
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    first_locked = asyncio.Event()
    release_first = asyncio.Event()
    second_backend_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()

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
            pid_result = await session.execute(text("SELECT pg_backend_pid()"))
            second_backend_pid.set_result(pid_result.scalar_one())
            return await repo.get_for_update(ROADMAP_ID)

    try:
        first_task = asyncio.create_task(first_writer())
        await asyncio.wait_for(first_locked.wait(), timeout=2)
        second_task = asyncio.create_task(second_writer())
        backend_pid = await asyncio.wait_for(asyncio.shield(second_backend_pid), timeout=2)
        await asyncio.wait_for(_wait_for_lock_wait(migrated_url, backend_pid), timeout=2)
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
