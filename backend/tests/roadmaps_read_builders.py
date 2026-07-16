"""Shared builders for the read-projection tests.

A richer published :class:`Roadmap` than the progress builder: subsections carry
``description``s, multiple ``resources`` (varied types), track ``tags``, effort
estimates, and a prereq DAG, so the read projections (``Overview`` /
``NodeDetail`` / ``SectionPage`` / ``SearchHit``) and the ``concise|detailed``
switch can all be exercised from one fixture. Also a ``checked_reader`` factory
over the in-memory progress repository, matching how the wiring binds the real
one, so a contract test can drive per-section counts and per-item done-state.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from progress_fakes import InMemoryProgressRepository
from wren.roadmaps.schemas import (
    ChecklistItem,
    Resource,
    ResourceType,
    Roadmap,
    RoadmapStatus,
    Section,
    Subsection,
    Visibility,
)

_NOW = datetime(2026, 7, 15, tzinfo=UTC)

ROADMAP_ID = "grokking-dsa-7f3k"
AUTHOR = "author"

SUB_ARRAYS = "sub_arrays"
SUB_HASHING = "sub_hashing"
SUB_GRAPHS = "sub_graphs"
CHK_ARRAYS_READ = "chk_arrays-read"
CHK_ARRAYS_DRILL = "chk_arrays-drill"
CHK_HASH = "chk_hash"
CHK_GRAPHS = "chk_graphs"
RES_ARRAYS_GUIDE = "res_arrays-guide"
RES_ARRAYS_VIDEO = "res_arrays-video"

ALL_ITEM_IDS = frozenset({CHK_ARRAYS_READ, CHK_ARRAYS_DRILL, CHK_HASH, CHK_GRAPHS})


def _resource(res_id: str, title: str, res_type: ResourceType) -> Resource:
    return Resource(id=res_id, title=title, url=f"https://x.test/{res_id}", type=res_type)


def build_read_roadmap(
    *,
    roadmap_id: str = ROADMAP_ID,
    owner: str = AUTHOR,
    status: RoadmapStatus = RoadmapStatus.PUBLISHED,
    visibility: Visibility = Visibility.PUBLIC,
) -> Roadmap:
    """A two-section published roadmap with descriptions, varied resources, tags,
    a prereq DAG, and a valid ``suggested_path`` (arrays -> hashing -> graphs).

    Four checklist items total (arrays has two, the rest one each)."""
    arrays = Subsection(
        id=SUB_ARRAYS,
        title="Arrays",
        description="Two-pointer and sliding-window patterns.",
        tags=["arrays", "two-pointers"],
        effort_estimate="3h",
        prereq_ids=[],
        resources={
            RES_ARRAYS_GUIDE: _resource(RES_ARRAYS_GUIDE, "Arrays guide", ResourceType.ARTICLE),
            RES_ARRAYS_VIDEO: _resource(RES_ARRAYS_VIDEO, "Arrays video", ResourceType.VIDEO),
        },
        resource_order=[RES_ARRAYS_GUIDE, RES_ARRAYS_VIDEO],
        checklist_items={
            CHK_ARRAYS_READ: ChecklistItem(id=CHK_ARRAYS_READ, text="Read the arrays chapter"),
            CHK_ARRAYS_DRILL: ChecklistItem(id=CHK_ARRAYS_DRILL, text="Drill two-pointer problems"),
        },
        item_order=[CHK_ARRAYS_READ, CHK_ARRAYS_DRILL],
    )
    hashing = Subsection(
        id=SUB_HASHING,
        title="Hashing",
        description="Hash maps and sets.",
        tags=["hashing"],
        effort_estimate="2h",
        prereq_ids=[SUB_ARRAYS],
        resources={
            "res_hashing-doc": _resource("res_hashing-doc", "Hashing docs", ResourceType.DOCS)
        },
        resource_order=["res_hashing-doc"],
        checklist_items={CHK_HASH: ChecklistItem(id=CHK_HASH, text="Implement a hash map")},
        item_order=[CHK_HASH],
    )
    graphs = Subsection(
        id=SUB_GRAPHS,
        title="Graphs",
        description="BFS and DFS traversal.",
        tags=["graphs"],
        prereq_ids=[SUB_HASHING],
        resources={
            "res_graphs-book": _resource("res_graphs-book", "Graphs book", ResourceType.BOOK)
        },
        resource_order=["res_graphs-book"],
        checklist_items={CHK_GRAPHS: ChecklistItem(id=CHK_GRAPHS, text="Traverse a graph")},
        item_order=[CHK_GRAPHS],
    )
    core = Section(
        id="sec_core",
        title="Core",
        subsections={SUB_ARRAYS: arrays, SUB_HASHING: hashing},
        subsection_order=[SUB_ARRAYS, SUB_HASHING],
    )
    advanced = Section(
        id="sec_advanced",
        title="Advanced",
        subsections={SUB_GRAPHS: graphs},
        subsection_order=[SUB_GRAPHS],
    )
    return Roadmap(
        id=roadmap_id,
        owner=owner,
        title="Grokking DSA",
        description="A structured path through data structures and algorithms.",
        subject_tags=["cs"],
        visibility=visibility,
        status=status,
        revision=1,
        sections={"sec_core": core, "sec_advanced": advanced},
        section_order=["sec_core", "sec_advanced"],
        suggested_path=[SUB_ARRAYS, SUB_HASHING, SUB_GRAPHS],
        created_at=_NOW,
        updated_at=_NOW,
    )


CheckedReader = Callable[[str, str], Awaitable[frozenset[str]]]


def checked_reader_over(progress_repo: InMemoryProgressRepository) -> CheckedReader:
    """A :data:`~wren.roadmaps.read_service.CheckedReader` over the in-memory progress
    repository, mirroring how the production wiring binds it: returns the caller's
    checked item ids for ``(user_id, roadmap_id)`` (empty when they have no
    record), so a contract test's Overview counts and NodeDetail done-state follow
    real per-user progress rows."""

    async def read(user_id: str, roadmap_id: str) -> frozenset[str]:
        record = await progress_repo.get(user_id, roadmap_id)
        if record is None:
            return frozenset()
        return frozenset(item_id for item_id, is_checked in record.checked.items() if is_checked)

    return read
