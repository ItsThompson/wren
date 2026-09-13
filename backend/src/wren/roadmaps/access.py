"""Shared roadmap readability policy."""

from __future__ import annotations

from wren.roadmaps.schemas import Roadmap, RoadmapStatus, Visibility


def can_read(roadmap: Roadmap, user_id: str | None) -> bool:
    """Return whether a resolved reader may retrieve the roadmap document."""
    if user_id is not None and roadmap.owner == user_id:
        return True
    return roadmap.visibility is Visibility.PUBLIC and roadmap.status in {
        RoadmapStatus.PUBLISHED,
        RoadmapStatus.ARCHIVED,
    }
