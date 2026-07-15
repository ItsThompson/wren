"""Roadmaps domain constants (spec sections 04, 06).

Entity slug prefixes and the roadmap-ID minting bounds are domain truths shared
by the pure ``slugs``/``assembly`` modules and the service, so they live in one
place rather than being re-decided per call site.
"""

from __future__ import annotations

# The external REST mount point. Roadmaps are addressed by the
# flat global route ``/roadmaps/{id}``.
ROADMAPS_PATH = "/roadmaps"

# Server-minted slug prefixes, one per child entity (spec section 04 slug rules).
# The roadmap ID itself has no prefix (it carries a random token instead).
SECTION_PREFIX = "sec_"
SUBSECTION_PREFIX = "sub_"
CHECKLIST_PREFIX = "chk_"
RESOURCE_PREFIX = "res_"

# On the astronomically unlikely global collision of a freshly minted roadmap ID,
# the service silently re-rolls the random token. This bounds the loop so a
# pathological repository (always reporting a collision) can never spin forever;
# with a 32^4 token space a real run resolves on the first attempt.
MAX_ID_MINT_ATTEMPTS = 8

# Server-set page size for the paginated section drill-down (spec sections 06/07:
# the server sets the page size; the client pages with an opaque cursor). Injected
# into RoadmapService (overridable in tests to force truncation on a small fixture).
SECTION_PAGE_SIZE = 20
