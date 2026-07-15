"""Unit tests for the pure ``progress.next`` deep module (spec sections 05/07).

``next.compute`` is pure over the roadmap + progress, so it is tested in complete
isolation (no DB, request, or token). Covers the walk down ``suggested_path``,
the done-skip, the prereq gate, completion, and the defensive draft-only edges.
"""

from __future__ import annotations

from datetime import UTC, datetime

from progress_builders import (
    CHK_ARRAYS_DRILL,
    CHK_ARRAYS_READ,
    CHK_GRAPHS,
    CHK_HASH,
    SUB_ARRAYS,
    SUB_GRAPHS,
    SUB_HASHING,
    build_roadmap,
)
from wren.progress.next import compute
from wren.progress.schemas import Progress
from wren.roadmaps.schemas import (
    ChecklistItem,
    Roadmap,
    RoadmapStatus,
    Section,
    Subsection,
    Visibility,
)

_NOW = datetime(2026, 7, 15, tzinfo=UTC)


def _progress(*checked_ids: str) -> Progress:
    return Progress(
        user_id="learner",
        roadmap_id="grokking-dsa-7f3k",
        checked=dict.fromkeys(checked_ids, True),
        updated_at=_NOW,
    )


def test_first_subsection_items_are_next_when_nothing_is_checked() -> None:
    result = compute(build_roadmap(), _progress())
    assert result.complete is False
    assert [item.item_id for item in result.items] == [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL]
    assert all(item.subsection_id == SUB_ARRAYS for item in result.items)
    # Resource links travel with the next item (links, never inlined bodies).
    assert result.items[0].resources[0].url == f"https://x.test/{SUB_ARRAYS}"


def test_only_the_unchecked_items_of_the_current_subsection_are_returned() -> None:
    # Arrays is partway done: only the still-unchecked item is next.
    result = compute(build_roadmap(), _progress(CHK_ARRAYS_READ))
    assert [item.item_id for item in result.items] == [CHK_ARRAYS_DRILL]
    assert result.complete is False


def test_advances_to_the_next_subsection_once_the_current_one_is_done() -> None:
    result = compute(build_roadmap(), _progress(CHK_ARRAYS_READ, CHK_ARRAYS_DRILL))
    assert [item.subsection_id for item in result.items] == [SUB_HASHING]
    assert [item.item_id for item in result.items] == [CHK_HASH]


def test_advances_across_sections_following_the_path() -> None:
    result = compute(build_roadmap(), _progress(CHK_ARRAYS_READ, CHK_ARRAYS_DRILL, CHK_HASH))
    assert [item.subsection_id for item in result.items] == [SUB_GRAPHS]
    assert result.complete is False


def test_reports_completion_when_every_item_is_checked() -> None:
    result = compute(
        build_roadmap(), _progress(CHK_ARRAYS_READ, CHK_ARRAYS_DRILL, CHK_HASH, CHK_GRAPHS)
    )
    assert result.complete is True
    assert result.items == []


def test_a_stale_checked_id_is_ignored() -> None:
    # An id not in the roadmap (content edited before publish) does not count.
    result = compute(build_roadmap(), _progress("chk_ghost"))
    assert [item.item_id for item in result.items] == [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL]


def _two_node_roadmap(path: list[str]) -> Roadmap:
    """Arrays + Hashing (hashing needs arrays), with a caller-chosen path."""
    section = Section(
        id="sec_x",
        title="X",
        subsections={
            "sub_a": Subsection(
                id="sub_a",
                title="Arrays",
                prereq_ids=[],
                checklist_items={"chk_a": ChecklistItem(id="chk_a", text="a")},
                item_order=["chk_a"],
            ),
            "sub_b": Subsection(
                id="sub_b",
                title="Hashing",
                prereq_ids=["sub_a"],
                checklist_items={"chk_b": ChecklistItem(id="chk_b", text="b")},
                item_order=["chk_b"],
            ),
        },
        subsection_order=["sub_a", "sub_b"],
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
        suggested_path=path,
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_skips_a_subsection_whose_prerequisites_are_not_done() -> None:
    # Path lists hashing first, but its prereq (arrays) is not done, so arrays is
    # surfaced instead (prereq-satisfied wins over raw path position).
    roadmap = _two_node_roadmap(["sub_b", "sub_a"])
    result = compute(roadmap, _progress())
    assert [item.item_id for item in result.items] == ["chk_a"]


def test_returns_nothing_available_when_all_remaining_are_blocked() -> None:
    # Only hashing is in the path and its prereq (arrays) can never be reached via
    # the path, so nothing is available yet and it is not complete.
    roadmap = _two_node_roadmap(["sub_b"])
    result = compute(roadmap, _progress())
    assert result.items == []
    assert result.complete is False


def test_unknown_path_id_is_skipped() -> None:
    roadmap = _two_node_roadmap(["sub_ghost", "sub_a", "sub_b"])
    result = compute(roadmap, _progress())
    assert [item.item_id for item in result.items] == ["chk_a"]


def test_order_arrays_out_of_sync_with_their_maps_are_skipped() -> None:
    # A defensive edge: an item_order / resource_order id with no entry in the
    # backing map is skipped rather than raising (pure-module robustness).
    section = Section(
        id="sec_x",
        title="X",
        subsections={
            "sub_a": Subsection(
                id="sub_a",
                title="Arrays",
                prereq_ids=[],
                resources={},
                resource_order=["res_ghost"],
                checklist_items={"chk_a": ChecklistItem(id="chk_a", text="a")},
                item_order=["chk_a", "chk_ghost"],
            ),
        },
        subsection_order=["sub_a"],
    )
    roadmap = Roadmap(
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
    result = compute(roadmap, _progress())
    # Only the real item is returned, and it carries no (missing) resource links.
    assert [item.item_id for item in result.items] == ["chk_a"]
    assert result.items[0].resources == []
