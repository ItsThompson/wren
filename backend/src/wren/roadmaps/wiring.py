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
from wren.roadmaps.repository import SqlAlchemyRoadmapRepository
from wren.roadmaps.service import RoadmapService


def build_roadmap_service_provider() -> Callable[[AsyncSession], RoadmapService]:
    """A FastAPI dependency that builds a request-scoped :class:`RoadmapService`."""

    def provider(session: AsyncSession = Depends(get_session)) -> RoadmapService:
        return RoadmapService(SqlAlchemyRoadmapRepository(session))

    return provider
