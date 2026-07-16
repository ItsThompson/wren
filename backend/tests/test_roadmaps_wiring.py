"""The roadmap service providers build request-scoped services."""

from __future__ import annotations

from wren.roadmaps.read_service import RoadmapReadService
from wren.roadmaps.service import RoadmapService
from wren.roadmaps.wiring import (
    build_roadmap_read_service_provider,
    build_roadmap_service_provider,
)


def test_provider_builds_a_service_for_a_session() -> None:
    provider = build_roadmap_service_provider()
    # The provider binds the repository to whatever session it is handed (FastAPI
    # supplies the request-scoped one at runtime); a placeholder proves the wiring.
    service = provider(session=object())  # type: ignore[arg-type]
    assert isinstance(service, RoadmapService)


def test_read_provider_builds_a_read_service_for_a_session() -> None:
    provider = build_roadmap_read_service_provider()
    # Same as the authoring provider: the read service binds its repository and
    # progress-backed checked reader to whatever request-scoped session it is handed.
    service = provider(session=object())  # type: ignore[arg-type]
    assert isinstance(service, RoadmapReadService)
