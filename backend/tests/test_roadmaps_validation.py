"""Structural validation deep-module tests (spec sections 04, 05, 13).

Exercises ``validate_structure`` through its public function over hand-built
``Roadmap`` objects: exhaustive per-rule cases for the full contract (V1..V8),
the all-in-one-pass guarantee (several rules surface together, never fail-fast),
a well-formed draft returning ``[]``, and two ``hypothesis`` properties: a valid
draft never violates, and a draft carrying a single seeded defect surfaces
exactly that violation.
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
    prereqs: list[str] | None = None,
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
        prereq_ids=prereqs or [],
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


# --- V1: the prerequisite DAG is acyclic ------------------------------------


def test_v1_flags_a_self_edge_as_a_trivial_cycle() -> None:
    sub = _subsection("sub_x", prereqs=["sub_x"])
    roadmap = _roadmap(sections=[_section(subsections=[sub])], suggested_path=["sub_x"])

    v1 = [v for v in validate_structure(roadmap) if v.rule == StructuralRule.V1_ACYCLIC]

    assert len(v1) == 1
    assert v1[0].ids == ["sub_x"]
    # The dag module's CycleReport message is carried verbatim (section 06 shape).
    assert v1[0].message == "prerequisite cycle: sub_x -> sub_x"


def test_v1_reports_a_multi_node_cycle_with_distinct_ids() -> None:
    # sub_a depends on sub_c, sub_c on sub_b, sub_b on sub_a: a 3-node cycle. The
    # V1 ids are the distinct nodes of the closed walk (the loop-closing repeat
    # of the first node is dropped), matching the section 06 shape.
    subs = [
        _subsection("sub_a", prereqs=["sub_c"]),
        _subsection("sub_b", prereqs=["sub_a"]),
        _subsection("sub_c", prereqs=["sub_b"]),
    ]
    roadmap = _roadmap(
        sections=[_section(subsections=subs)],
        suggested_path=["sub_a", "sub_b", "sub_c"],
    )

    v1 = next(v for v in validate_structure(roadmap) if v.rule == StructuralRule.V1_ACYCLIC)

    assert set(v1.ids) == {"sub_a", "sub_b", "sub_c"}
    assert len(v1.ids) == len(set(v1.ids))


# --- V2: no dangling prereq_ids ---------------------------------------------


def test_v2_flags_a_dangling_prereq_naming_owner_and_reference() -> None:
    sub = _subsection("sub_a", prereqs=["sub_ghost"])
    roadmap = _roadmap(sections=[_section(subsections=[sub])], suggested_path=["sub_a"])

    v2 = [v for v in validate_structure(roadmap) if v.rule == StructuralRule.V2_NO_DANGLING_PREREQ]

    assert len(v2) == 1
    assert v2[0].ids == ["sub_a", "sub_ghost"]
    assert "sub_ghost" in v2[0].message


# --- V3: suggested_path covers every subsection exactly once ----------------


def test_v3_flags_an_empty_path_as_missing_every_subsection() -> None:
    roadmap = _roadmap(suggested_path=[])

    v3 = next(v for v in validate_structure(roadmap) if v.rule == StructuralRule.V3_PATH_COVERAGE)

    assert v3.ids == ["sub_arrays"]
    assert "missing" in v3.message


def test_v3_flags_a_missing_subsection() -> None:
    subs = [_subsection("sub_a"), _subsection("sub_b")]
    roadmap = _roadmap(sections=[_section(subsections=subs)], suggested_path=["sub_a"])

    v3 = [v for v in validate_structure(roadmap) if v.rule == StructuralRule.V3_PATH_COVERAGE]

    assert [v.ids for v in v3] == [["sub_b"]]
    assert "missing" in v3[0].message


def test_v3_flags_a_duplicated_subsection() -> None:
    subs = [_subsection("sub_a"), _subsection("sub_b")]
    roadmap = _roadmap(
        sections=[_section(subsections=subs)],
        suggested_path=["sub_a", "sub_b", "sub_a"],
    )

    v3 = [v for v in validate_structure(roadmap) if v.rule == StructuralRule.V3_PATH_COVERAGE]

    assert [v.ids for v in v3] == [["sub_a"]]
    assert "more than once" in v3[0].message


def test_v3_flags_an_unknown_path_entry() -> None:
    roadmap = _roadmap(suggested_path=["sub_arrays", "sub_ghost"])

    v3 = [v for v in validate_structure(roadmap) if v.rule == StructuralRule.V3_PATH_COVERAGE]

    assert [v.ids for v in v3] == [["sub_ghost"]]
    assert "unknown" in v3[0].message


def test_v3_stays_silent_when_there_are_no_subsections() -> None:
    # An empty roadmap fails V5, but has nothing to sequence, so V3 stays silent.
    roadmap = _roadmap(sections=[_section(subsections=[])], suggested_path=[])
    assert StructuralRule.V3_PATH_COVERAGE not in _rules(roadmap)


# --- V4: suggested_path is a legal topological order ------------------------


def test_v4_flags_an_out_of_order_prerequisite() -> None:
    # sub_b depends on sub_a, but the path lists sub_b before its prerequisite.
    subs = [_subsection("sub_a"), _subsection("sub_b", prereqs=["sub_a"])]
    roadmap = _roadmap(
        sections=[_section(subsections=subs)],
        suggested_path=["sub_b", "sub_a"],
    )

    v4 = [v for v in validate_structure(roadmap) if v.rule == StructuralRule.V4_PATH_ORDER]

    assert len(v4) == 1
    assert v4[0].ids == ["sub_a", "sub_b"]
    assert "sub_a" in v4[0].message
    assert "sub_b" in v4[0].message


# --- all violations in one pass ---------------------------------------------


def test_dag_and_content_violations_return_together_in_one_pass() -> None:
    # A self-edge cycle (V1) on a subsection that also lacks items (V6) and
    # resources (V7), inside a blank-titled section (V8): every independent rule
    # surfaces in a single pass rather than fail-fast on the first.
    bad = _subsection("sub_x", prereqs=["sub_x"], with_item=False, with_resource=False)
    roadmap = _roadmap(sections=[_section(title="", subsections=[bad])], suggested_path=["sub_x"])

    rules = set(_rules(roadmap))

    assert rules == {
        StructuralRule.V1_ACYCLIC,
        StructuralRule.V6_ITEM_REQUIRED,
        StructuralRule.V7_RESOURCE_REQUIRED,
        StructuralRule.V8_TITLE_REQUIRED,
    }


def test_v7_violation_matches_the_section_06_wire_example() -> None:
    # Mirrors the section 06 422 example entry exactly: rule + ids + message.
    sub = _subsection("sub_two-pointers", with_resource=False)
    roadmap = _roadmap(sections=[_section(subsections=[sub])], suggested_path=["sub_two-pointers"])

    v7 = [v for v in validate_structure(roadmap) if v.rule == StructuralRule.V7_RESOURCE_REQUIRED]

    assert v7[0].ids == ["sub_two-pointers"]
    assert v7[0].message == "subsection sub_two-pointers has no resources"


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


# --- property: a single seeded defect surfaces exactly that violation -------


@st.composite
def _valid_chain(draw: st.DrawFn) -> Roadmap:
    """A valid roadmap: one section holding a prerequisite chain
    ``sub_0 <- sub_1 <- ...`` (each depends on the previous), every subsection
    with a title, a resource and an item, and ``suggested_path`` equal to the
    chain order (a legal topological order). Passes ``validate_structure``.
    """
    length = draw(st.integers(min_value=2, max_value=5))
    subsections = [
        _subsection(f"sub_{i}", title=f"Step {i}", prereqs=[f"sub_{i - 1}"] if i else [])
        for i in range(length)
    ]
    return _roadmap(
        sections=[_section(subsections=subsections)],
        suggested_path=[f"sub_{i}" for i in range(length)],
    )


@st.composite
def _chain_with_one_defect(draw: st.DrawFn) -> tuple[Roadmap, StructuralRule]:
    """Draw a valid chain and inject exactly one structural defect, returning the
    mutated roadmap and the single rule it must surface."""
    roadmap = draw(_valid_chain()).model_copy(deep=True)
    rule = draw(st.sampled_from(list(StructuralRule)))
    section = roadmap.sections[roadmap.section_order[0]]
    head = section.subsections["sub_0"]
    path = list(roadmap.suggested_path)

    if rule is StructuralRule.V1_ACYCLIC:
        head.prereq_ids = ["sub_0"]  # self-edge: a trivial cycle
    elif rule is StructuralRule.V2_NO_DANGLING_PREREQ:
        head.prereq_ids = ["sub_ghost"]  # references a node that does not exist
    elif rule is StructuralRule.V3_PATH_COVERAGE:
        roadmap.suggested_path = path[:-1]  # drop the leaf: no longer covered
    elif rule is StructuralRule.V4_PATH_ORDER:
        path[0], path[1] = path[1], path[0]  # sub_1 now precedes its prereq sub_0
        roadmap.suggested_path = path
    elif rule is StructuralRule.V5_SUBSECTION_REQUIRED:
        roadmap.sections["sec_empty"] = Section(id="sec_empty", title="Empty")
        roadmap.section_order.append("sec_empty")
    elif rule is StructuralRule.V6_ITEM_REQUIRED:
        head.checklist_items = {}
        head.item_order = []
    elif rule is StructuralRule.V7_RESOURCE_REQUIRED:
        head.resources = {}
        head.resource_order = []
    else:  # StructuralRule.V8_TITLE_REQUIRED
        roadmap.title = ""

    return roadmap, rule


@given(_chain_with_one_defect())
def test_a_single_seeded_defect_surfaces_exactly_that_violation(
    bundle: tuple[Roadmap, StructuralRule],
) -> None:
    roadmap, expected_rule = bundle
    rules = {violation.rule for violation in validate_structure(roadmap)}
    assert rules == {expected_rule}
