"""Unit tests for the shared section-completion counting helper.

``count_section``/``percent`` were byte-identical copies in
``roadmaps.projections`` and ``progress.summary``; hoisted into ``core`` (over
``AbstractSet[str]``) they are single-sourced. This suite is the one helper test
that replaces the two former copies' coverage; the projections and summary
suites keep exercising the helper through their public builders (sociable).
"""

from __future__ import annotations

from wren.core.section_counts import count_section, percent
from wren.roadmaps.schemas import ChecklistItem, Section, Subsection


def _section(*item_ids: str) -> Section:
    """A one-subsection section whose checklist ``item_order`` is ``item_ids``."""
    items = {item_id: ChecklistItem(id=item_id, text=item_id) for item_id in item_ids}
    return Section(
        id="sec_x",
        title="X",
        subsections={
            "sub_x": Subsection(
                id="sub_x",
                title="Sub X",
                checklist_items=items,
                item_order=list(item_ids),
            )
        },
        subsection_order=["sub_x"],
    )


def test_count_section_tallies_total_and_checked() -> None:
    section = _section("chk_a", "chk_b", "chk_c")
    assert count_section(section, frozenset({"chk_a", "chk_c"})) == (3, 2)


def test_count_section_accepts_both_set_and_frozenset() -> None:
    # The hoisted helper takes AbstractSet[str], so progress (set) and roadmaps
    # (frozenset) both pass their checked-id set without adapting: this is the
    # annotation-drift resolution the L1 change settles.
    section = _section("chk_a", "chk_b")
    assert count_section(section, {"chk_a"}) == (2, 1)
    assert count_section(section, frozenset({"chk_a"})) == (2, 1)


def test_count_section_of_an_item_less_section_is_zero_zero() -> None:
    assert count_section(_section(), frozenset()) == (0, 0)


def test_percent_rounds_and_guards_against_a_zero_total() -> None:
    assert percent(1, 3) == 33
    assert percent(2, 3) == 67
    assert percent(5, 5) == 100
    assert percent(0, 5) == 0
    # An item-less collection is 0%, never a ZeroDivisionError.
    assert percent(0, 0) == 0
