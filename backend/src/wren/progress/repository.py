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

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from wren.core.db import fetch_optional
from wren.progress.models import ProgressRecord
from wren.progress.schemas import Progress


class ProgressRepository(Protocol):
    """Data access for progress, scoped to the operations the service needs."""

    async def get(self, user_id: str, roadmap_id: str) -> ProgressRecord | None: ...

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
