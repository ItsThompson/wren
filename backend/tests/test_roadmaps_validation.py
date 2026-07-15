"""Structural validation deep-module tests (spec sections 04, 05, 13).

Exercises ``validate_structure`` through its public function over hand-built
``Roadmap`` objects: exhaustive per-rule cases for the minimal subset (V5-V8 plus
the minimal V3 suggested_path gate), the all-in-one-pass contract, and a
property-based check that a well-formed draft never raises.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from wren.roadmaps.schemas import (
    ChecklistItem,
    Resource,
    ResourceType,
    Roadmap,
    Section,
    Subsection,
)
from wren.roadmaps.validation import StructuralRule, validate_structure

_NOW = datetime(2026, 7, 15, tzinfo=UTC)


def _subsection(
    sub_id: str = "sub_arrays",
    *,
    title: str = "Arrays",
    with_resource: bool = True,
    with_item: bool = True,
) -> Subsection:
    resources = (
        {
            "res_g": Resource(
                id="res_g", title="Guide", url="https://x.test", type=ResourceType.ARTICLE
            )
        }
        if with_resource
        else {}
    )
    items = {"chk_r": ChecklistItem(id="chk_r", text="Read it")} if with_item else {}
    return Subsection(
        id=sub_id,
        title=title,
        resources=resources,
        resource_order=list(resources),
        checklist_items=items,
        item_order=list(items),
    )


def _roadmap(
    *,
    title: str = "Grokking DSA",
    sections: list[Section] | None = None,
    suggested_path: list[str] | None = None,
) -> Roadmap:
    section_list = sections if sections is not None else [_section()]
    return Roadmap(
        id="grokking-dsa-7f3k",
        owner="user-1",
        title=title,
        sections={section.id: section for section in section_list},
        section_order=[section.id for section in section_list],
        suggested_path=suggested_path if suggested_path is not None else ["sub_arrays"],
        created_at=_NOW,
        updated_at=_NOW,
    )


def _section(
    section_id: str = "sec_foundations",
    *,
    title: str = "Foundations",
    subsections: list[Subsection] | None = None,
) -> Section:
    sub_list = subsections if subsections is not None else [_subsection()]
    return Section(
        id=section_id,
        title=title,
        subsections={sub.id: sub for sub in sub_list},
        subsection_order=[sub.id for sub in sub_list],
    )


def _rules(roadmap: Roadmap) -> list[str]:
    return [violation.rule for violation in validate_structure(roadmap)]


# --- a well-formed draft passes ---------------------------------------------


def test_a_well_formed_draft_has_no_violations() -> None:
    assert validate_structure(_roadmap()) == []


# --- V8: non-empty titles ---------------------------------------------------


def test_v8_flags_an_empty_roadmap_title() -> None:
    violations = validate_structure(_roadmap(title="  "))
    assert [v.rule for v in violations] == [StructuralRule.V8_TITLE_REQUIRED]
    assert violations[0].ids == ["grokking-dsa-7f3k"]


def test_v8_flags_an_empty_section_title() -> None:
    roadmap = _roadmap(sections=[_section(title="")])
    violations = [
        v for v in validate_structure(roadmap) if v.rule == StructuralRule.V8_TITLE_REQUIRED
    ]
    assert [v.ids for v in violations] == [["sec_foundations"]]


def test_v8_flags_an_empty_subsection_title() -> None:
    roadmap = _roadmap(sections=[_section(subsections=[_subsection(title="")])])
    flagged = [
        v.ids for v in validate_structure(roadmap) if v.rule == StructuralRule.V8_TITLE_REQUIRED
    ]
    assert flagged == [["sub_arrays"]]


def test_v8_flags_an_empty_checklist_item_text() -> None:
    sub = Subsection(
        id="sub_arrays",
        title="Arrays",
        resources={
            "res_g": Resource(
                id="res_g", title="G", url="https://x.test", type=ResourceType.ARTICLE
            )
        },
        resource_order=["res_g"],
        checklist_items={"chk_blank": ChecklistItem(id="chk_blank", text="")},
        item_order=["chk_blank"],
    )
    roadmap = _roadmap(sections=[_section(subsections=[sub])], suggested_path=["sub_arrays"])
    flagged = [
        v.ids for v in validate_structure(roadmap) if v.rule == StructuralRule.V8_TITLE_REQUIRED
    ]
    assert flagged == [["chk_blank"]]


# --- V5: every section has >= 1 subsection ----------------------------------


def test_v5_flags_a_section_with_no_subsections() -> None:
    roadmap = _roadmap(sections=[_section(subsections=[])], suggested_path=[])
    rules = _rules(roadmap)
    assert StructuralRule.V5_SUBSECTION_REQUIRED in rules
    v5 = next(
        v for v in validate_structure(roadmap) if v.rule == StructuralRule.V5_SUBSECTION_REQUIRED
    )
    assert v5.ids == ["sec_foundations"]


# --- V6: every subsection has >= 1 checklist item ---------------------------


def test_v6_flags_a_subsection_with_no_items() -> None:
    roadmap = _roadmap(sections=[_section(subsections=[_subsection(with_item=False)])])
    v6 = [v for v in validate_structure(roadmap) if v.rule == StructuralRule.V6_ITEM_REQUIRED]
    assert [v.ids for v in v6] == [["sub_arrays"]]


# --- V7: every subsection has >= 1 resource ---------------------------------


def test_v7_flags_a_subsection_with_no_resources() -> None:
    roadmap = _roadmap(sections=[_section(subsections=[_subsection(with_resource=False)])])
    v7 = [v for v in validate_structure(roadmap) if v.rule == StructuralRule.V7_RESOURCE_REQUIRED]
    assert [v.ids for v in v7] == [["sub_arrays"]]


# --- V3 (minimal): suggested_path present -----------------------------------


def test_v3_flags_an_empty_suggested_path_when_subsections_exist() -> None:
    roadmap = _roadmap(suggested_path=[])
    v3 = next(v for v in validate_structure(roadmap) if v.rule == StructuralRule.V3_PATH_COVERAGE)
    # Names every subsection as missing from the (empty) path.
    assert v3.ids == ["sub_arrays"]


def test_v3_passes_a_nonempty_path_without_checking_coverage() -> None:
    # Minimal gate: a present-but-incomplete path passes here; full coverage +
    # topological order are deferred to the dag composition (later slice).
    roadmap = _roadmap(suggested_path=["sub_arrays", "sub_unrelated"])
    assert StructuralRule.V3_PATH_COVERAGE not in _rules(roadmap)


def test_v3_does_not_require_a_path_when_there_are_no_subsections() -> None:
    # An empty roadmap fails V5, but has nothing to sequence, so V3 stays silent.
    roadmap = _roadmap(sections=[_section(subsections=[])], suggested_path=[])
    assert StructuralRule.V3_PATH_COVERAGE not in _rules(roadmap)


# --- all violations in one pass ---------------------------------------------


def test_validate_returns_every_violation_in_one_pass() -> None:
    # A subsection missing both a resource and an item, in a roadmap with a blank
    # title: three distinct rules surface together (never fail-fast).
    bad_sub = _subsection(with_resource=False, with_item=False)
    roadmap = _roadmap(title="", sections=[_section(subsections=[bad_sub])])
    rules = set(_rules(roadmap))
    assert {
        StructuralRule.V8_TITLE_REQUIRED,
        StructuralRule.V6_ITEM_REQUIRED,
        StructuralRule.V7_RESOURCE_REQUIRED,
    } <= rules


def test_stale_order_ids_are_skipped_defensively() -> None:
    # Order arrays referencing missing keys (a ghost section / subsection / item)
    # must be skipped without crashing the structural walk. The rest of the draft
    # is well-formed, so validation stays clean.
    sub = Subsection(
        id="sub_present",
        title="Present",
        resources={
            "res_g": Resource(
                id="res_g", title="G", url="https://x.test", type=ResourceType.ARTICLE
            )
        },
        resource_order=["res_g"],
        checklist_items={"chk_present": ChecklistItem(id="chk_present", text="Do it")},
        item_order=["chk_present", "chk_ghost"],
    )
    section = Section(
        id="sec_present",
        title="Present",
        subsections={"sub_present": sub},
        subsection_order=["sub_present", "sub_ghost"],
    )
    roadmap = Roadmap(
        id="grokking-dsa-7f3k",
        owner="user-1",
        title="Grokking DSA",
        sections={"sec_present": section},
        section_order=["sec_present", "sec_ghost"],
        suggested_path=["sub_present"],
        created_at=_NOW,
        updated_at=_NOW,
    )
    assert validate_structure(roadmap) == []


# --- property: a valid draft never produces violations ----------------------


@given(
    title=st.text(min_size=1).filter(lambda text: text.strip()),
    n_items=st.integers(min_value=1, max_value=4),
)
def test_property_a_complete_draft_is_always_valid(title: str, n_items: int) -> None:
    items = {f"chk_{i}": ChecklistItem(id=f"chk_{i}", text=f"item {i}") for i in range(n_items)}
    sub = Subsection(
        id="sub_arrays",
        title=title,
        resources={
            "res_g": Resource(
                id="res_g", title="G", url="https://x.test", type=ResourceType.ARTICLE
            )
        },
        resource_order=["res_g"],
        checklist_items=items,
        item_order=list(items),
    )
    roadmap = _roadmap(
        title=title,
        sections=[_section(title=title, subsections=[sub])],
        suggested_path=["sub_arrays"],
    )
    assert validate_structure(roadmap) == []
