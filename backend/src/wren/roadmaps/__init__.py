"""The roadmaps domain: authoring spine for learning roadmaps.

Mirrors the accounts domain layout (config / models / schemas / repository /
service / api / wiring) plus the pure deep modules the service composes
(``slugs`` for ID minting, ``assembly`` for turning ordered authoring input into
the persisted ID-keyed structure).

``__all__`` is the curated cross-domain surface: the contract types other domains
(notably ``progress``) legitimately consume, so those consumers bind to this
package surface rather than deep-importing ``roadmaps.schemas``. The shared
``concise | detailed`` read switch lives in
:class:`wren.core.read_contract.ResponseFormat`, not here.
"""

from wren.roadmaps.schemas import (
    ResourceType,
    Roadmap,
    RoadmapStatus,
    Section,
    Subsection,
    Visibility,
)

__all__ = [
    "ResourceType",
    "Roadmap",
    "RoadmapStatus",
    "Section",
    "Subsection",
    "Visibility",
]
