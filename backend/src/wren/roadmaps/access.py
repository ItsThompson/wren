"""Shared roadmap readability policy."""

from __future__ import annotations

from wren.roadmaps.schemas import Roadmap, RoadmapStatus, Visibility


def can_read(roadmap: Roadmap, user_id: str) -> bool:
    """Return whether ``user_id`` may retrieve the roadmap document."""
    if roadmap.owner == user_id:
        return True
    return roadmap.visibility is Visibility.PUBLIC and roadmap.status is not RoadmapStatus.DRAFT
