"""Shared roadmap readability policy."""

from __future__ import annotations

from wren.roadmaps.schemas import PublishedVisibility, Roadmap, RoadmapStatus


def can_read(roadmap: Roadmap, user_id: str | None) -> bool:
    """Return whether a resolved reader may retrieve the roadmap document."""
    if user_id is not None and roadmap.owner == user_id:
        return True
    return roadmap.published_visibility is PublishedVisibility.PUBLIC and roadmap.status in {
        RoadmapStatus.PUBLISHED,
        RoadmapStatus.ARCHIVED,
    }
