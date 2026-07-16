"""Compose the progress dependency graph for the external + internal apps.

Keeps the wiring (which request-scoped session backs the repositories) out of the
router and the entrypoint. The provider resolves a per-request ``AsyncSession``
via ``get_session`` and binds both the roadmaps read repository (for the
published/readable + item-validation reads) and the progress repository over the
same session, so both live in one transaction. The service's clock keeps its
process-wide default.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from wren.core.db import get_session
from wren.progress.repository import SqlAlchemyProgressRepository
from wren.progress.service import ProgressService

# Cross-domain coupling: progress composes the concrete roadmap repository for
# its read access. Genuine coupling, not a missing re-export; a shared read-port
# abstraction is a known follow-up.
from wren.roadmaps.repository import SqlAlchemyRoadmapRepository


def build_progress_service_provider() -> Callable[[AsyncSession], ProgressService]:
    """A FastAPI dependency that builds a request-scoped :class:`ProgressService`."""

    def provider(session: AsyncSession = Depends(get_session)) -> ProgressService:
        return ProgressService(
            SqlAlchemyRoadmapRepository(session),
            SqlAlchemyProgressRepository(session),
        )

    return provider
