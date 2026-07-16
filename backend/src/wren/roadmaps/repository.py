"""Roadmap persistence: the repository interface and its SQLAlchemy binding.

The service depends on the :class:`RoadmapRepository` interface and receives a
resolved ``user_id``; it never builds queries itself. Tests
substitute an in-memory repository at this interface; production binds
:class:`SqlAlchemyRoadmapRepository` over a request-scoped ``AsyncSession``.

Transaction ownership: ``core.db.get_session`` is yield-only, so the service
calls :meth:`commit`/:meth:`rollback` here. Reads are **owner-scoped** at the
query level (``WHERE id = :id AND owner = :owner``), so a non-owner's request for
a private draft resolves to ``None`` -> 404, leaking no existence.
``roadmap_id_exists`` is deliberately global (across all owners): it
backs the mint-time uniqueness check for the globally-unique roadmap ID and
returns only a boolean, never another user's data.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Protocol

from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from wren.core.db import fetch_optional
from wren.roadmaps.models import RoadmapRecord
from wren.roadmaps.schemas import Roadmap, RoadmapStatus, Visibility


class RoadmapRepository(Protocol):
    """Data access for roadmaps, scoped to the operations the service needs."""

    async def roadmap_id_exists(self, roadmap_id: str) -> bool: ...

    async def add(self, record: RoadmapRecord) -> None: ...

    async def save(self, roadmap: Roadmap) -> None: ...

    async def delete(self, roadmap_id: str) -> None: ...

    async def get(self, roadmap_id: str) -> RoadmapRecord | None: ...

    async def get_owned(self, roadmap_id: str, owner_id: str) -> RoadmapRecord | None: ...

    async def list_owned(self, owner_id: str) -> list[RoadmapRecord]: ...

    async def list_published_public(self, owner_id: str) -> list[RoadmapRecord]: ...

    async def list_by_ids(self, roadmap_ids: Sequence[str]) -> list[RoadmapRecord]: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


@asynccontextmanager
async def transaction(repo: RoadmapRepository) -> AsyncIterator[None]:
    """Single-source the roadmaps write invariant: commit on a clean exit, roll
    back and re-raise on any error.

    The caller performs an arbitrary mutate (``add``/``save``/``delete``) inside
    the ``async with`` block; this boundary commits it, or rolls back and
    re-raises if the block raised. Replaces the ``try/commit/except/rollback``
    idiom that was inlined at every write site (mirrors
    :meth:`wren.progress.service.ProgressService._persist`, generalized to wrap
    any mutate rather than a hard-coded repo method).
    """
    try:
        yield
        await repo.commit()
    except Exception:
        await repo.rollback()
        raise


class SqlAlchemyRoadmapRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def roadmap_id_exists(self, roadmap_id: str) -> bool:
        found = await fetch_optional(
            self._session, select(RoadmapRecord.id).where(RoadmapRecord.id == roadmap_id)
        )
        return found is not None

    async def add(self, record: RoadmapRecord) -> None:
        self._session.add(record)
        # Flush so a PK collision surfaces as an IntegrityError now, inside the
        # service's try/except, rather than at commit time.
        await self._session.flush()

    async def save(self, roadmap: Roadmap) -> None:
        """Persist an update to an existing roadmap from the domain object.

        Re-derives every write-managed column from the authoritative ``document``
        so the scalar index cannot drift (``updated_at`` is set explicitly, which
        also suppresses the column's ``onupdate`` so the persisted value matches
        the returned roadmap). The row must already exist (created via ``add``).
        """
        await self._session.execute(
            update(RoadmapRecord)
            .where(RoadmapRecord.id == roadmap.id)
            .values(
                owner=roadmap.owner,
                title=roadmap.title,
                status=roadmap.status.value,
                visibility=roadmap.visibility.value,
                revision=roadmap.revision,
                document=roadmap.model_dump(mode="json"),
                updated_at=roadmap.updated_at,
            )
        )
        await self._session.flush()

    async def delete(self, roadmap_id: str) -> None:
        """Remove a roadmap row by id (the web-only delete).

        The service enforces the zero-followers guard before calling this, so the
        row is deleted unconditionally here. Progress rows are keyed separately by
        ``(user_id, roadmap_id)`` and are not touched: a delete is only reached when
        no progress rows reference the roadmap.
        """
        await self._session.execute(sa_delete(RoadmapRecord).where(RoadmapRecord.id == roadmap_id))
        await self._session.flush()

    async def get_owned(self, roadmap_id: str, owner_id: str) -> RoadmapRecord | None:
        return await fetch_optional(
            self._session,
            select(RoadmapRecord).where(
                RoadmapRecord.id == roadmap_id, RoadmapRecord.owner == owner_id
            ),
        )

    async def get(self, roadmap_id: str) -> RoadmapRecord | None:
        """Load a roadmap by id without owner scoping.

        Unlike :meth:`get_owned`, this is not scoped to a caller: it backs the
        cross-user reads the progress domain needs (a follower reading a
        published roadmap they do not own). Callers apply
        their own readability rule (published/public vs owner) before using the
        result, so this accessor never itself grants access.
        """
        return await fetch_optional(
            self._session, select(RoadmapRecord).where(RoadmapRecord.id == roadmap_id)
        )

    async def list_owned(self, owner_id: str) -> list[RoadmapRecord]:
        """Every roadmap owned by ``owner_id`` at any status, newest-touched first.

        Backs the dashboard "Yours" section: the
        owner sees their own drafts, private, and public roadmaps. Scoped to the
        owner at the query level, so it returns only the caller's own roadmaps.
        """
        result = await self._session.scalars(
            select(RoadmapRecord)
            .where(RoadmapRecord.owner == owner_id)
            .order_by(RoadmapRecord.updated_at.desc(), RoadmapRecord.id)
        )
        return list(result)

    async def list_published_public(self, owner_id: str) -> list[RoadmapRecord]:
        """``owner_id``'s **published, public** roadmaps, newest-touched first.

        Backs the public profile: drafts, private,
        and archived roadmaps are excluded at the query level, so a profile can
        never leak a non-public roadmap regardless of who is viewing.
        """
        result = await self._session.scalars(
            select(RoadmapRecord)
            .where(
                RoadmapRecord.owner == owner_id,
                RoadmapRecord.status == RoadmapStatus.PUBLISHED.value,
                RoadmapRecord.visibility == Visibility.PUBLIC.value,
            )
            .order_by(RoadmapRecord.updated_at.desc(), RoadmapRecord.id)
        )
        return list(result)

    async def list_by_ids(self, roadmap_ids: Sequence[str]) -> list[RoadmapRecord]:
        """Load the given roadmaps by id (unscoped), for the dashboard "Following"
        section.

        Unscoped like :meth:`get`: the caller's authorization to see a followed
        roadmap is their own progress row (keyed to their ``user_id``), resolved by
        the listing service, so this never itself grants access. The caller
        re-orders the result by the follow order; an empty input returns ``[]``
        without a query.
        """
        if not roadmap_ids:
            return []
        result = await self._session.scalars(
            select(RoadmapRecord).where(RoadmapRecord.id.in_(roadmap_ids))
        )
        return list(result)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
