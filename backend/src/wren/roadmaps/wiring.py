"""Compose the roadmaps dependency graph for the external app.

Keeps the wiring (which request-scoped session backs the repository) out of the
router and the entrypoint. The production provider resolves a per-request
``AsyncSession`` via ``get_session`` and binds the SQLAlchemy repository; the
service's token factory and clock keep their process-wide defaults.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from wren.core.db import get_session
from wren.progress.repository import SqlAlchemyProgressRepository
from wren.roadmaps.repository import SqlAlchemyRoadmapRepository
from wren.roadmaps.service import CheckedReader, RoadmapService


def build_roadmap_service_provider() -> Callable[[AsyncSession], RoadmapService]:
    """A FastAPI dependency that builds a request-scoped :class:`RoadmapService`."""

    def provider(session: AsyncSession = Depends(get_session)) -> RoadmapService:
        # The follower counter and the checked reader are bound to the progress
        # repository over the SAME request-scoped session (delete's zero-followers
        # guard, spec sections 05/06; and the caller's checked set for the
        # progress-aware read projections). The roadmaps service stays decoupled
        # from the progress domain: it only receives the narrow callables, not the
        # repository.
        progress_repo = SqlAlchemyProgressRepository(session)
        return RoadmapService(
            SqlAlchemyRoadmapRepository(session),
            follower_counter=progress_repo.count_followers,
            checked_reader=_checked_reader(progress_repo),
        )

    return provider


def _checked_reader(progress_repo: SqlAlchemyProgressRepository) -> CheckedReader:
    """Adapt the progress repository into the narrow :data:`CheckedReader`.

    Returns the caller's checked checklist-item ids for ``(user_id, roadmap_id)``
    (an empty set when they have no progress record), so a read projection can
    compute per-section counts and per-item done-state without the roadmaps domain
    importing the progress repository's type into its own logic."""

    async def read(user_id: str, roadmap_id: str) -> frozenset[str]:
        record = await progress_repo.get(user_id, roadmap_id)
        if record is None:
            return frozenset()
        return frozenset(item_id for item_id, is_checked in record.checked.items() if is_checked)

    return read
