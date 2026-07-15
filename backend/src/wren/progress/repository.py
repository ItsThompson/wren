"""Progress persistence: the repository interface and its SQLAlchemy binding.

The service depends on the :class:`ProgressRepository` interface and receives a
resolved ``user_id`` (never trusted from args); it never builds queries itself
(spec section 05). Tests substitute an in-memory repository at this interface;
production binds :class:`SqlAlchemyProgressRepository` over a request-scoped
``AsyncSession`` (shared with the roadmaps read repository, so both live in one
transaction).

Transaction ownership: ``core.db.get_session`` is yield-only, so the service
calls :meth:`commit`/:meth:`rollback` here. Every read is scoped to the resolved
``(user_id, roadmap_id)``; another user's progress is never returned (spec
section 05 per-user scoping). :meth:`upsert` writes the one row for that pair,
making both follow (first write) and repeated updates idempotent.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from wren.core.db import fetch_optional
from wren.progress.models import ProgressRecord
from wren.progress.schemas import Progress


class ProgressRepository(Protocol):
    """Data access for progress, scoped to the operations the service needs."""

    async def get(self, user_id: str, roadmap_id: str) -> ProgressRecord | None: ...

    async def list_followed_roadmap_ids(self, user_id: str) -> list[str]: ...

    async def count_followers(self, roadmap_id: str) -> int: ...

    async def upsert(self, progress: Progress) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class SqlAlchemyProgressRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: str, roadmap_id: str) -> ProgressRecord | None:
        return await fetch_optional(
            self._session,
            select(ProgressRecord).where(
                ProgressRecord.user_id == user_id, ProgressRecord.roadmap_id == roadmap_id
            ),
        )

    async def list_followed_roadmap_ids(self, user_id: str) -> list[str]:
        """The roadmap ids ``user_id`` follows, most-recently-updated first.

        Caller-scoped (``WHERE user_id = :user_id``): it returns only the ids of
        the caller's own progress rows, never another user's, so it can back the
        dashboard "Following" list without leaking anyone else's follows (spec
        sections 02/08). The composite PK keys one row per (user, roadmap), so the
        ids are already distinct.
        """
        result = await self._session.scalars(
            select(ProgressRecord.roadmap_id)
            .where(ProgressRecord.user_id == user_id)
            .order_by(ProgressRecord.updated_at.desc(), ProgressRecord.roadmap_id)
        )
        return list(result)

    async def count_followers(self, roadmap_id: str) -> int:
        """Count the progress rows referencing ``roadmap_id`` (its follower count).

        Global across all users (not caller-scoped): it returns only a count, never
        another user's data, and backs the roadmaps domain's delete guard
        (delete-only-if-zero-followers, spec sections 05/06). The ``roadmap_id``
        index added in migration 0005 keeps this a cheap indexed count.
        """
        count = await self._session.scalar(
            select(func.count())
            .select_from(ProgressRecord)
            .where(ProgressRecord.roadmap_id == roadmap_id)
        )
        return count or 0

    async def upsert(self, progress: Progress) -> None:
        """Insert or update the one row for ``(user_id, roadmap_id)``.

        The composite primary key makes this idempotent: following an
        already-followed roadmap or replaying an update writes the same row.
        ``created_at`` stays at its insert value (only ``deadline`` / ``checked``
        / ``updated_at`` are refreshed on conflict)."""
        statement = (
            pg_insert(ProgressRecord)
            .values(
                user_id=progress.user_id,
                roadmap_id=progress.roadmap_id,
                deadline=progress.deadline,
                checked=progress.checked,
                updated_at=progress.updated_at,
            )
            .on_conflict_do_update(
                index_elements=[ProgressRecord.user_id, ProgressRecord.roadmap_id],
                set_={
                    "deadline": progress.deadline,
                    "checked": progress.checked,
                    "updated_at": progress.updated_at,
                },
            )
        )
        await self._session.execute(statement)
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
