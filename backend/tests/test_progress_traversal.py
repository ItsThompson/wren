"""Unit tests for the pure ``progress.traversal`` helpers (spec sections 04/05).

Locks in the canonical "which items exist" source: ``item_order`` (the
addressable order array), matching the counting/done/next helpers. For a
published roadmap the order array and the ``checklist_items`` map agree; these
tests pin the chosen source on the defensive edge where they diverge.
"""

from __future__ import annotations

from datetime import UTC, datetime

from wren.progress.schemas import Progress
from wren.progress.traversal import all_item_ids, checked_item_ids
from wren.roadmaps.schemas import (
    ChecklistItem,
    Roadmap,
    RoadmapStatus,
    Section,
    Subsection,
    Visibility,
)

_NOW = datetime(2026, 7, 15, tzinfo=UTC)


def _roadmap(item_order: list[str], checklist_ids: list[str]) -> Roadmap:
    subsection = Subsection(
        id="sub_a",
        title="A",
        prereq_ids=[],
        checklist_items={cid: ChecklistItem(id=cid, text=cid) for cid in checklist_ids},
        item_order=item_order,
    )
    section = Section(
        id="sec_x", title="X", subsections={"sub_a": subsection}, subsection_order=["sub_a"]
    )
    return Roadmap(
        id="r-0000",
        owner="owner",
        title="R",
        visibility=Visibility.PUBLIC,
        status=RoadmapStatus.PUBLISHED,
        revision=1,
        sections={"sec_x": section},
        section_order=["sec_x"],
        suggested_path=["sub_a"],
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_all_item_ids_uses_item_order_as_the_canonical_source() -> None:
    # chk_b is present in the map but absent from item_order: it is unaddressable
    # and every derived read ignores it, so all_item_ids excludes it.
    roadmap = _roadmap(item_order=["chk_a"], checklist_ids=["chk_a", "chk_b"])
    assert all_item_ids(roadmap) == {"chk_a"}


def test_checked_item_ids_only_counts_ids_from_item_order() -> None:
    roadmap = _roadmap(item_order=["chk_a"], checklist_ids=["chk_a", "chk_b"])
    progress = Progress(
        user_id="u", roadmap_id="r-0000", checked={"chk_a": True, "chk_b": True}, updated_at=_NOW
    )
    # chk_b is not addressable (not in item_order), so it is not counted.
    assert checked_item_ids(roadmap, progress) == {"chk_a"}
