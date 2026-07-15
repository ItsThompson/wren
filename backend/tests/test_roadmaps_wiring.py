"""The roadmap service provider builds a request-scoped service."""

from __future__ import annotations

from wren.roadmaps.service import RoadmapService
from wren.roadmaps.wiring import build_roadmap_service_provider


def test_provider_builds_a_service_for_a_session() -> None:
    provider = build_roadmap_service_provider()
    # The provider binds the repository to whatever session it is handed (FastAPI
    # supplies the request-scoped one at runtime); a placeholder proves the wiring.
    service = provider(session=object())  # type: ignore[arg-type]
    assert isinstance(service, RoadmapService)
