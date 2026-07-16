"""Unit tests for the pure ``progress.next`` deep module.

``next.compute`` is pure over the roadmap + progress, so it is tested in complete
isolation (no DB, request, or token). Covers the walk down ``suggested_path``,
the done-skip, the prereq gate, completion, and the defensive draft-only edges.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

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
from wren.core.read_contract import ResponseFormat
from wren.progress.next import compute
from wren.progress.schemas import Progress
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


# --- why_now: structural rationale only -------------------


def test_why_now_states_no_prerequisites_for_a_root_subsection() -> None:
    result = compute(build_roadmap(), _progress())
    assert result.items[0].subsection_id == SUB_ARRAYS
    assert result.items[0].why_now == (
        "Next unchecked subsection in the suggested path; it has no prerequisites."
    )


def test_why_now_names_the_completed_prerequisites() -> None:
    # After arrays is done, hashing (whose prereq is arrays) is next.
    result = compute(build_roadmap(), _progress(CHK_ARRAYS_READ, CHK_ARRAYS_DRILL))
    assert result.items[0].subsection_id == SUB_HASHING
    assert result.items[0].why_now == (
        "Next unchecked subsection in the suggested path; prerequisites sub_arrays are complete."
    )


# Words that would betray a pedagogical / ZPD judgement (which must live in the
# agent, never in the app): why_now states mechanical facts only (spec 01/07).
_PEDAGOGICAL_WORDS = (
    "difficult",
    "difficulty",
    "easy",
    "hard",
    "ready",
    "recommend",
    "should",
    "beginner",
    "advanced",
    "zpd",
    "challenging",
    "master",
    "understand",
    "foundational",
    "effort",
    "pace",
    "behind",
    "ahead",
)


def test_why_now_contains_no_pedagogical_judgment() -> None:
    # Every next item on a fully-walked roadmap: only structural facts, no ZPD.
    for checked in (
        [],
        [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL],
        [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL, CHK_HASH],
    ):
        result = compute(build_roadmap(), _progress(*checked))
        for item in result.items:
            lowered = item.why_now.lower()
            assert "suggested path" in lowered
            for word in _PEDAGOGICAL_WORDS:
                assert word not in lowered, (
                    f"why_now leaked pedagogical word {word!r}: {item.why_now!r}"
                )


# --- path_position: detailed mode only --------------------------------------


def test_path_position_is_absent_in_concise_mode() -> None:
    result = compute(build_roadmap(), _progress())
    assert result.items != []
    assert all(item.path_position is None for item in result.items)


def test_path_position_is_the_subsection_index_in_the_path_when_detailed() -> None:
    # Arrays is the first entry in suggested_path -> position 1 for all its items.
    first = compute(build_roadmap(), _progress(), fmt=ResponseFormat.DETAILED)
    assert all(item.path_position == 1 for item in first.items)
    # After arrays is done, hashing (second in the path) is next -> position 2.
    second = compute(
        build_roadmap(), _progress(CHK_ARRAYS_READ, CHK_ARRAYS_DRILL), fmt=ResponseFormat.DETAILED
    )
    assert second.items[0].subsection_id == SUB_HASHING
    assert second.items[0].path_position == 2


# --- remaining_in_path ------------------------------------------------------


def test_remaining_in_path_counts_every_subsection_still_to_do() -> None:
    # Nothing checked: all three subsections in the path remain.
    assert compute(build_roadmap(), _progress()).remaining_in_path == 3


def test_remaining_in_path_decrements_as_subsections_are_completed() -> None:
    # Arrays fully done -> two remain (hashing, graphs); the current node still counts.
    result = compute(build_roadmap(), _progress(CHK_ARRAYS_READ, CHK_ARRAYS_DRILL))
    assert result.remaining_in_path == 2


def test_remaining_in_path_is_zero_when_complete() -> None:
    result = compute(
        build_roadmap(), _progress(CHK_ARRAYS_READ, CHK_ARRAYS_DRILL, CHK_HASH, CHK_GRAPHS)
    )
    assert result.complete is True
    assert result.remaining_in_path == 0


# --- property: every returned item is unchecked with prereqs done -----------


@st.composite
def _roadmap_and_progress(draw: st.DrawFn) -> tuple[Roadmap, Progress]:
    """A prerequisite-chain roadmap (``sub_0 <- sub_1 <- ...``, each depending on
    the previous) with a valid ``suggested_path`` and a random subset of its items
    marked checked. Models "any roadmap + progress" for the property-based invariant."""
    length = draw(st.integers(min_value=1, max_value=5))
    subsections: dict[str, Subsection] = {}
    order: list[str] = []
    all_items: list[str] = []
    for i in range(length):
        item_ids = [f"chk_{i}_{j}" for j in range(draw(st.integers(min_value=1, max_value=3)))]
        all_items.extend(item_ids)
        sub_id = f"sub_{i}"
        subsections[sub_id] = Subsection(
            id=sub_id,
            title=f"Step {i}",
            prereq_ids=[f"sub_{i - 1}"] if i else [],
            resources={
                f"res_{i}": Resource(
                    id=f"res_{i}", title="R", url=f"https://x.test/{i}", type=ResourceType.ARTICLE
                )
            },
            resource_order=[f"res_{i}"],
            checklist_items={iid: ChecklistItem(id=iid, text=iid) for iid in item_ids},
            item_order=item_ids,
        )
        order.append(sub_id)
    roadmap = Roadmap(
        id="r-0000",
        owner="owner",
        title="R",
        visibility=Visibility.PUBLIC,
        status=RoadmapStatus.PUBLISHED,
        revision=1,
        sections={
            "sec_x": Section(id="sec_x", title="X", subsections=subsections, subsection_order=order)
        },
        section_order=["sec_x"],
        suggested_path=list(order),
        created_at=_NOW,
        updated_at=_NOW,
    )
    checked_ids = draw(st.lists(st.sampled_from(all_items), unique=True))
    progress = Progress(
        user_id="learner",
        roadmap_id="r-0000",
        checked=dict.fromkeys(checked_ids, True),
        updated_at=_NOW,
    )
    return roadmap, progress


@given(_roadmap_and_progress())
def test_property_every_returned_item_is_unchecked_with_prereqs_done(
    bundle: tuple[Roadmap, Progress],
) -> None:
    roadmap, progress = bundle
    checked = {item_id for item_id, is_checked in progress.checked.items() if is_checked}
    subsections = {
        sub_id: subsection
        for section in roadmap.sections.values()
        for sub_id, subsection in section.subsections.items()
    }
    all_items = {iid for sub in subsections.values() for iid in sub.item_order}

    result = compute(roadmap, progress, fmt=ResponseFormat.DETAILED)

    # complete iff every item is checked.
    assert result.complete is (all_items <= checked)
    for item in result.items:
        # every returned item is unchecked ...
        assert item.item_id not in checked
        # ... and its subsection's prerequisites are all done.
        for prereq_id in subsections[item.subsection_id].prereq_ids:
            prereq = subsections[prereq_id]
            assert all(iid in checked for iid in prereq.item_order)
