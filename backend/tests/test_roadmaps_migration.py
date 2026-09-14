"""Integration tests: the roadmaps migration and repository against real Postgres.

Applies Alembic to head on a containerized ``postgres:17-alpine`` and exercises
the SQLAlchemy repository + service end to end, so the JSONB document round-trip,
owner-scoped reads, and the global roadmap-ID existence check run against the
real asyncpg driver. Skipped automatically when Docker is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, NotRequired, TypedDict

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

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

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]


class LegacyRow(TypedDict):
    id: str
    visibility: str
    document: object
    owner: NotRequired[str]
    title: NotRequired[str]
    status: NotRequired[str]
    revision: NotRequired[int]


class PublishedRow(TypedDict):
    id: str
    published_visibility: str
    document: object
    owner: NotRequired[str]
    title: NotRequired[str]
    status: NotRequired[str]
    revision: NotRequired[int]


@pytest.fixture
def isolated_migration_url(postgres_url: str) -> Iterator[str]:
    """Provide a disposable database for staged migration tests."""
    database_name = f"roadmaps_migration_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_execute(postgres_url, f'CREATE DATABASE "{database_name}"'))
    target_url = (
        make_url(postgres_url).set(database=database_name).render_as_string(hide_password=False)
    )
    try:
        yield target_url
    finally:
        asyncio.run(
            _admin_execute(postgres_url, f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        )


def _alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _run_migration(url: str, target: str) -> None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(_alembic_config(url), target)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _run_downgrade(url: str, target: str) -> None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.downgrade(_alembic_config(url), target)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


async def _admin_execute(admin_url: str, statement: str) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text(statement))
    finally:
        await engine.dispose()


async def _seed_legacy_rows(url: str, rows: list[LegacyRow]) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            for row in rows:
                await conn.execute(
                    text(
                        "INSERT INTO roadmaps "
                        "(id, owner, title, status, visibility, revision, document) "
                        "VALUES (:id, :owner, :title, :status, :visibility, :revision, "
                        "CAST(:document AS jsonb))"
                    ),
                    {
                        "id": row["id"],
                        "owner": row.get("owner", "migration-owner"),
                        "title": row.get("title", row["id"]),
                        "status": row.get("status", "draft"),
                        "visibility": row["visibility"],
                        "revision": row.get("revision", 1),
                        "document": json.dumps(row["document"]),
                    },
                )
    finally:
        await engine.dispose()


async def _fetch_rows(url: str, query: str) -> list[dict[str, object]]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(query))
            return [dict(row._mapping) for row in result]
    finally:
        await engine.dispose()


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
                published_visibility="private",
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


def test_staged_upgrade_and_downgrade_preserve_rows_and_latest_values(
    isolated_migration_url: str,
) -> None:
    _run_migration(isolated_migration_url, "0006_onboarding")
    legacy_rows: list[LegacyRow] = [
        {
            "id": "legacy-public",
            "status": "draft",
            "visibility": "public",
            "document": {"status": "draft", "visibility": "public"},
        },
        {
            "id": "legacy-private",
            "status": "published",
            "visibility": "private",
            "document": {"status": "published", "visibility": "private"},
        },
        {
            "id": "legacy-missing-key",
            "status": "archived",
            "visibility": "private",
            "document": {"status": "archived"},
        },
    ]
    asyncio.run(_seed_legacy_rows(isolated_migration_url, legacy_rows))

    before = asyncio.run(
        _fetch_rows(
            isolated_migration_url,
            "SELECT id, owner, title, status, revision, document FROM roadmaps ORDER BY id",
        )
    )
    _run_migration(isolated_migration_url, "0007_published_visibility")
    upgraded_columns = asyncio.run(
        _fetch_rows(
            isolated_migration_url,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'roadmaps' AND column_name = 'published_visibility'",
        )
    )
    assert upgraded_columns == [{"column_name": "published_visibility"}]
    upgraded = asyncio.run(
        _fetch_rows(
            isolated_migration_url,
            "SELECT id, owner, title, status, revision, published_visibility, document "
            "FROM roadmaps ORDER BY id",
        )
    )
    assert len(upgraded) == len(before) == 3
    assert [(row["id"], row["status"]) for row in upgraded] == [
        ("legacy-missing-key", "archived"),
        ("legacy-private", "published"),
        ("legacy-public", "draft"),
    ]
    upgraded_by_id = {row["id"]: row for row in upgraded}
    assert upgraded_by_id["legacy-missing-key"]["published_visibility"] == "private"
    assert (
        _document_fields(upgraded_by_id["legacy-missing-key"])["published_visibility"] == "private"
    )
    assert _document_fields(upgraded_by_id["legacy-private"])["published_visibility"] == "private"

    published_rows: list[PublishedRow] = [
        {
            "id": "new-0007-public",
            "status": "draft",
            "published_visibility": "public",
            "document": {"status": "draft", "published_visibility": "public"},
        },
        {
            "id": "new-0007-private",
            "status": "published",
            "published_visibility": "private",
            "document": {"status": "published", "published_visibility": "private"},
        },
    ]
    asyncio.run(_seed_published_rows(isolated_migration_url, published_rows))
    asyncio.run(_update_published_row(isolated_migration_url, "legacy-public", "private"))
    asyncio.run(_update_published_row(isolated_migration_url, "legacy-private", "public"))
    _run_downgrade(isolated_migration_url, "0006_onboarding")
    downgraded_columns = asyncio.run(
        _fetch_rows(
            isolated_migration_url,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'roadmaps' AND column_name = 'visibility'",
        )
    )
    assert downgraded_columns == [{"column_name": "visibility"}]
    downgraded = asyncio.run(
        _fetch_rows(
            isolated_migration_url,
            "SELECT id, status, visibility, document FROM roadmaps ORDER BY id",
        )
    )
    assert len(downgraded) == 5
    downgraded_by_id = {row["id"]: row for row in downgraded}
    assert downgraded_by_id["legacy-public"]["visibility"] == "private"
    assert _document_fields(downgraded_by_id["legacy-public"])["visibility"] == "private"
    assert downgraded_by_id["legacy-private"]["visibility"] == "public"
    assert _document_fields(downgraded_by_id["legacy-private"])["visibility"] == "public"
    assert downgraded_by_id["legacy-missing-key"]["visibility"] == "private"
    assert _document_fields(downgraded_by_id["legacy-missing-key"])["visibility"] == "private"
    assert downgraded_by_id["new-0007-public"]["visibility"] == "public"
    assert _document_fields(downgraded_by_id["new-0007-public"])["visibility"] == "public"
    assert downgraded_by_id["new-0007-private"]["visibility"] == "private"
    assert _document_fields(downgraded_by_id["new-0007-private"])["visibility"] == "private"


def _document_fields(row: dict[str, object]) -> dict[str, object]:
    document = row["document"]
    assert isinstance(document, dict)
    return document


async def _seed_published_rows(url: str, rows: list[PublishedRow]) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            for row in rows:
                await conn.execute(
                    text(
                        "INSERT INTO roadmaps "
                        "(id, owner, title, status, published_visibility, revision, document) "
                        "VALUES (:id, :owner, :title, :status, :published_visibility, :revision, "
                        "CAST(:document AS jsonb))"
                    ),
                    {
                        "id": row["id"],
                        "owner": row.get("owner", "migration-owner"),
                        "title": row.get("title", row["id"]),
                        "status": row.get("status", "draft"),
                        "published_visibility": row["published_visibility"],
                        "revision": row.get("revision", 1),
                        "document": json.dumps(row["document"]),
                    },
                )
    finally:
        await engine.dispose()


async def _update_published_row(url: str, roadmap_id: str, visibility: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE roadmaps SET published_visibility = :visibility, "
                    "document = jsonb_set(document, '{published_visibility}', "
                    "to_jsonb(CAST(:visibility AS text))) WHERE id = :id"
                ),
                {"id": roadmap_id, "visibility": visibility},
            )
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("visibility", "document"),
    [
        ("secret", {"status": "draft", "visibility": "public"}),
        ("public", {"status": "draft", "visibility": "private"}),
        ("public", {"status": "draft", "visibility": "secret"}),
        ("public", {"status": "draft", "visibility": 42}),
        ("public", {"status": "draft", "published_visibility": "private"}),
        (
            "public",
            {"status": "draft", "visibility": "public", "published_visibility": "public"},
        ),
        ("public", ["not", "an", "object"]),
    ],
    ids=[
        "invalid-scalar",
        "scalar-document-drift",
        "invalid-legacy-value",
        "invalid-legacy-type",
        "destination-key",
        "both-keys",
        "non-object-document",
    ],
)
def test_upgrade_preflight_rejects_without_mutating_rows(
    isolated_migration_url: str,
    visibility: str,
    document: object,
) -> None:
    _run_migration(isolated_migration_url, "0006_onboarding")
    preflight_row: LegacyRow = {
        "id": "preflight-row",
        "visibility": visibility,
        "document": document,
    }
    asyncio.run(_seed_legacy_rows(isolated_migration_url, [preflight_row]))
    before = asyncio.run(
        _fetch_rows(
            isolated_migration_url,
            "SELECT * FROM roadmaps",
        )
    )

    with pytest.raises(Exception, match="published visibility migration preflight failed"):
        _run_migration(isolated_migration_url, "0007_published_visibility")

    after = asyncio.run(
        _fetch_rows(
            isolated_migration_url,
            "SELECT * FROM roadmaps",
        )
    )
    assert after == before
    version = asyncio.run(
        _fetch_rows(isolated_migration_url, "SELECT version_num FROM alembic_version")
    )
    assert version == [{"version_num": "0006_onboarding"}]
    columns = asyncio.run(
        _fetch_rows(
            isolated_migration_url,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'roadmaps' AND column_name = 'published_visibility'",
        )
    )
    assert columns == []
