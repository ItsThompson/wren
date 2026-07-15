"""Exhaustive + property-based tests for the pure ``patch`` deep module.

The primary iterative-edit path, so it is covered like the
other pure deep modules: every op type, atomic all-or-nothing
rollback on a mid-batch failure, model-recoverable errors that name valid
siblings / explain a cycle, ``before_id``/``after_id`` positioning + reorder,
``proposed_id`` de-dup remap and intra-batch reference resolution, idempotency of
the set/update/remove-edge ops, and ``hypothesis`` invariants (inverse ops
round-trip; any batch with one invalid op leaves the draft unchanged).

The applier is exercised through the public :func:`patch.apply`; the draft under
test is built by the real ``assemble_draft`` so the fixtures are realistic
(sociable, spec section 13).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from wren.roadmaps import patch
from wren.roadmaps.assembly import assemble_draft
from wren.roadmaps.schemas import (
    AddEdgeOp,
    AddItemOp,
    AddSectionOp,
    AddSubsectionOp,
    ChangedNode,
    ChangedNodeKind,
    ChangeType,
    ChecklistItemInput,
    RemoveEdgeOp,
    RemoveItemOp,
    RemoveSectionOp,
    RemoveSubsectionOp,
    ReorderOp,
    ResourceInput,
    ResourceType,
    Roadmap,
    RoadmapInput,
    SectionInput,
    SetEffortOp,
    SetResourcesOp,
    SetSuggestedPathOp,
    SetTagsOp,
    SubsectionInput,
    UpdateItemOp,
    UpdateSectionOp,
    UpdateSubsectionOp,
)

_NOW = datetime(2026, 7, 15, tzinfo=UTC)


def _resource() -> ResourceInput:
    return ResourceInput(title="Guide", url="https://x.test", type=ResourceType.ARTICLE)


def _sub(
    title: str,
    proposed_id: str,
    *,
    prereq_ids: list[str] | None = None,
    items: int = 1,
) -> SubsectionInput:
    return SubsectionInput(
        proposed_id=proposed_id,
        title=title,
        prereq_ids=prereq_ids or [],
        resources=[_resource()],
        checklist_items=[ChecklistItemInput(text=f"{title} item {n}") for n in range(items)],
    )


def _draft() -> Roadmap:
    """A realistic two-section draft with a prereq chain and multiple items."""
    doc = RoadmapInput(
        title="Grokking DSA",
        suggested_path=["sub_arrays", "sub_hashing", "sub_graphs"],
        sections=[
            SectionInput(
                proposed_id="sec_basics",
                title="Basics",
                subsections=[
                    _sub("Arrays", "sub_arrays", items=2),
                    _sub("Hashing", "sub_hashing", prereq_ids=["sub_arrays"]),
                ],
            ),
            SectionInput(
                proposed_id="sec_advanced",
                title="Advanced",
                subsections=[_sub("Graphs", "sub_graphs", prereq_ids=["sub_hashing"])],
            ),
        ],
    )
    return assemble_draft(doc, "grokking-dsa-7f3k", owner="user-1", now=_NOW).roadmap


def _basics(roadmap: Roadmap):
    return roadmap.sections["sec_basics"]


def _arrays(roadmap: Roadmap):
    return roadmap.sections["sec_basics"].subsections["sub_arrays"]


# --- purity / atomicity -----------------------------------------------------


def test_apply_never_mutates_the_input_draft() -> None:
    draft = _draft()
    snapshot = draft.model_dump()
    patch.apply(draft, [SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=["x"])])
    assert draft.model_dump() == snapshot


def test_apply_does_not_bump_revision_that_is_the_services_job() -> None:
    outcome = patch.apply(
        _draft(), [SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=["x"])]
    )
    assert outcome.roadmap.revision == 1


def test_a_batch_with_one_invalid_op_applies_nothing() -> None:
    draft = _draft()
    snapshot = draft.model_dump()
    ops = [
        SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=["core"]),
        AddItemOp(op="add_item", subsection_id="sub_hashing", text="new"),
        SetTagsOp(op="set_tags", subsection_id="sub_ghost", tags=["boom"]),  # invalid
    ]
    with pytest.raises(patch.PatchError):
        patch.apply(draft, ops)
    # The input is untouched (working-copy-then-commit): the two valid ops did not
    # leak out because the third failed.
    assert draft.model_dump() == snapshot


def test_patch_error_is_scoped_to_the_failing_ops_index() -> None:
    ops = [
        SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=["core"]),
        UpdateItemOp(op="update_item", item_id="chk_ghost", text="x"),  # invalid, index 1
    ]
    with pytest.raises(patch.PatchError) as excinfo:
        patch.apply(_draft(), ops)
    assert excinfo.value.field == "operations[1].item_id"


# --- sections ---------------------------------------------------------------


def test_add_section_appends_by_default_and_mints_from_title() -> None:
    outcome = patch.apply(_draft(), [AddSectionOp(op="add_section", title="Wrap Up")])
    assert outcome.roadmap.section_order == ["sec_basics", "sec_advanced", "sec_wrap-up"]
    assert outcome.roadmap.sections["sec_wrap-up"].title == "Wrap Up"
    assert outcome.changed_nodes == [
        ChangedNode(kind=ChangedNodeKind.SECTION, id="sec_wrap-up", change=ChangeType.ADDED)
    ]


def test_add_section_before_id_positions_it() -> None:
    outcome = patch.apply(
        _draft(), [AddSectionOp(op="add_section", title="Intro", before_id="sec_basics")]
    )
    assert outcome.roadmap.section_order == ["sec_intro", "sec_basics", "sec_advanced"]


def test_add_section_after_id_positions_it() -> None:
    outcome = patch.apply(
        _draft(), [AddSectionOp(op="add_section", title="Mid", after_id="sec_basics")]
    )
    assert outcome.roadmap.section_order == ["sec_basics", "sec_mid", "sec_advanced"]


def test_add_section_honors_a_proposed_id() -> None:
    outcome = patch.apply(
        _draft(), [AddSectionOp(op="add_section", title="Wrap", proposed_id="sec_outro")]
    )
    assert "sec_outro" in outcome.roadmap.sections
    assert outcome.remap == {}


def test_add_section_before_unknown_sibling_names_valid_sections() -> None:
    with pytest.raises(patch.PatchError) as excinfo:
        patch.apply(_draft(), [AddSectionOp(op="add_section", title="X", before_id="sec_ghost")])
    assert excinfo.value.field == "operations[0].before_id"
    assert "sec_basics" in excinfo.value.message and "sec_advanced" in excinfo.value.message


def test_update_section_changes_title() -> None:
    outcome = patch.apply(
        _draft(), [UpdateSectionOp(op="update_section", section_id="sec_basics", title="Core")]
    )
    assert outcome.roadmap.sections["sec_basics"].title == "Core"


def test_update_section_unknown_id_names_valid_sections() -> None:
    with pytest.raises(patch.PatchError) as excinfo:
        patch.apply(
            _draft(), [UpdateSectionOp(op="update_section", section_id="sec_ghost", title="X")]
        )
    assert "sec_basics" in excinfo.value.message


def test_remove_section_drops_it_from_map_and_order() -> None:
    outcome = patch.apply(
        _draft(), [RemoveSectionOp(op="remove_section", section_id="sec_advanced")]
    )
    assert outcome.roadmap.section_order == ["sec_basics"]
    assert "sec_advanced" not in outcome.roadmap.sections


# --- subsections ------------------------------------------------------------


def test_add_subsection_appends_and_mints_children() -> None:
    op = AddSubsectionOp(
        op="add_subsection", section_id="sec_basics", subsection=_sub("Sorting", "sub_sorting")
    )
    outcome = patch.apply(_draft(), [op])
    section = _basics(outcome.roadmap)
    assert section.subsection_order == ["sub_arrays", "sub_hashing", "sub_sorting"]
    sorting = section.subsections["sub_sorting"]
    assert sorting.resource_order[0].startswith("res_")
    assert sorting.item_order[0].startswith("chk_")


def test_add_subsection_before_id_positions_within_section() -> None:
    op = AddSubsectionOp(
        op="add_subsection",
        section_id="sec_basics",
        subsection=_sub("Intro", "sub_intro"),
        before_id="sub_arrays",
    )
    outcome = patch.apply(_draft(), [op])
    assert _basics(outcome.roadmap).subsection_order == ["sub_intro", "sub_arrays", "sub_hashing"]


def test_add_subsection_deduped_proposed_id_is_reported_in_remap() -> None:
    # sub_arrays already exists in the draft, so a proposed collision de-dupes.
    op = AddSubsectionOp(
        op="add_subsection",
        section_id="sec_basics",
        subsection=_sub("Arrays II", "sub_arrays"),
    )
    outcome = patch.apply(_draft(), [op])
    assert outcome.remap == {"sub_arrays": "sub_arrays-2"}
    assert "sub_arrays-2" in _basics(outcome.roadmap).subsections


def test_add_subsection_prereqs_resolve_to_existing_ids() -> None:
    op = AddSubsectionOp(
        op="add_subsection",
        section_id="sec_advanced",
        subsection=_sub("Trees", "sub_trees", prereq_ids=["sub_arrays"]),
    )
    outcome = patch.apply(_draft(), [op])
    trees = outcome.roadmap.sections["sec_advanced"].subsections["sub_trees"]
    assert trees.prereq_ids == ["sub_arrays"]


def test_add_subsection_unknown_section_names_valid_sections() -> None:
    op = AddSubsectionOp(op="add_subsection", section_id="sec_ghost", subsection=_sub("X", "sub_x"))
    with pytest.raises(patch.PatchError) as excinfo:
        patch.apply(_draft(), [op])
    assert excinfo.value.field == "operations[0].section_id"
    assert "sec_basics" in excinfo.value.message


def test_update_subsection_updates_only_provided_fields() -> None:
    op = UpdateSubsectionOp(
        op="update_subsection", subsection_id="sub_arrays", description="Now with detail"
    )
    outcome = patch.apply(_draft(), [op])
    arrays = _arrays(outcome.roadmap)
    assert arrays.description == "Now with detail"
    # Title is untouched and the ID never changes on a metadata edit.
    assert arrays.title == "Arrays"
    assert arrays.id == "sub_arrays"


def test_update_subsection_can_clear_description_with_null() -> None:
    op = UpdateSubsectionOp(op="update_subsection", subsection_id="sub_arrays", description=None)
    outcome = patch.apply(_draft(), [op])
    assert _arrays(outcome.roadmap).description is None


def test_update_subsection_can_change_title_without_changing_id() -> None:
    op = UpdateSubsectionOp(
        op="update_subsection", subsection_id="sub_arrays", title="Arrays & Slices"
    )
    outcome = patch.apply(_draft(), [op])
    arrays = _arrays(outcome.roadmap)
    assert arrays.title == "Arrays & Slices"
    # The slug ID is stable across a rename.
    assert arrays.id == "sub_arrays"


def test_update_subsection_can_set_effort() -> None:
    op = UpdateSubsectionOp(
        op="update_subsection", subsection_id="sub_arrays", effort_estimate="4h"
    )
    outcome = patch.apply(_draft(), [op])
    assert _arrays(outcome.roadmap).effort_estimate == "4h"


def test_remove_subsection_drops_it_from_its_section() -> None:
    outcome = patch.apply(
        _draft(), [RemoveSubsectionOp(op="remove_subsection", subsection_id="sub_hashing")]
    )
    assert _basics(outcome.roadmap).subsection_order == ["sub_arrays"]
    assert "sub_hashing" not in _basics(outcome.roadmap).subsections


def test_set_tags_replaces_the_tag_list() -> None:
    outcome = patch.apply(
        _draft(), [SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=["core", "warmup"])]
    )
    assert _arrays(outcome.roadmap).tags == ["core", "warmup"]


def test_set_resources_replaces_resources_with_fresh_ids() -> None:
    op = SetResourcesOp(
        op="set_resources",
        subsection_id="sub_arrays",
        resources=[
            ResourceInput(title="Video", url="https://v.test", type=ResourceType.VIDEO),
            ResourceInput(title="Docs", url="https://d.test", type=ResourceType.DOCS),
        ],
    )
    outcome = patch.apply(_draft(), [op])
    arrays = _arrays(outcome.roadmap)
    assert len(arrays.resources) == 2
    assert arrays.resource_order == list(arrays.resources)
    assert [r.type for r in arrays.resources.values()] == [ResourceType.VIDEO, ResourceType.DOCS]


def test_set_effort_sets_and_clears() -> None:
    set_op = SetEffortOp(op="set_effort", subsection_id="sub_arrays", effort_estimate="3h")
    assert _arrays(patch.apply(_draft(), [set_op]).roadmap).effort_estimate == "3h"
    clear_op = SetEffortOp(op="set_effort", subsection_id="sub_arrays", effort_estimate=None)
    assert _arrays(patch.apply(_draft(), [clear_op]).roadmap).effort_estimate is None


# --- edges (and DAG cycle guard) --------------------------------------------


def test_add_edge_adds_a_prerequisite() -> None:
    # sub_graphs currently prereqs sub_hashing; add sub_arrays too.
    outcome = patch.apply(
        _draft(), [AddEdgeOp(op="add_edge", from_id="sub_arrays", to_id="sub_graphs")]
    )
    graphs = outcome.roadmap.sections["sec_advanced"].subsections["sub_graphs"]
    assert graphs.prereq_ids == ["sub_hashing", "sub_arrays"]


def test_add_edge_is_idempotent_no_duplicate_prereq() -> None:
    # sub_hashing already prereqs sub_arrays in the fixture.
    outcome = patch.apply(
        _draft(), [AddEdgeOp(op="add_edge", from_id="sub_arrays", to_id="sub_hashing")]
    )
    assert outcome.roadmap.sections["sec_basics"].subsections["sub_hashing"].prereq_ids == [
        "sub_arrays"
    ]


def test_add_edge_creating_a_cycle_is_rejected_with_an_explanation() -> None:
    # sub_arrays <- sub_hashing already; adding sub_hashing -> sub_arrays closes it.
    op = AddEdgeOp(op="add_edge", from_id="sub_hashing", to_id="sub_arrays")
    with pytest.raises(patch.PatchError) as excinfo:
        patch.apply(_draft(), [op])
    assert excinfo.value.field == "operations[0].to_id"
    assert "cycle" in excinfo.value.message
    assert "sub_arrays" in excinfo.value.message and "sub_hashing" in excinfo.value.message


def test_add_self_edge_is_rejected_as_a_trivial_cycle() -> None:
    op = AddEdgeOp(op="add_edge", from_id="sub_arrays", to_id="sub_arrays")
    with pytest.raises(patch.PatchError) as excinfo:
        patch.apply(_draft(), [op])
    assert "cycle" in excinfo.value.message


def test_add_edge_unknown_endpoint_names_valid_subsections() -> None:
    op = AddEdgeOp(op="add_edge", from_id="sub_ghost", to_id="sub_arrays")
    with pytest.raises(patch.PatchError) as excinfo:
        patch.apply(_draft(), [op])
    assert excinfo.value.field == "operations[0].from_id"
    assert "sub_arrays" in excinfo.value.message


def test_remove_edge_removes_a_prerequisite() -> None:
    outcome = patch.apply(
        _draft(), [RemoveEdgeOp(op="remove_edge", from_id="sub_arrays", to_id="sub_hashing")]
    )
    assert _basics(outcome.roadmap).subsections["sub_hashing"].prereq_ids == []


def test_remove_edge_is_idempotent_when_edge_absent() -> None:
    # sub_graphs does not prereq sub_arrays: removing it is a no-op, not an error.
    outcome = patch.apply(
        _draft(), [RemoveEdgeOp(op="remove_edge", from_id="sub_arrays", to_id="sub_graphs")]
    )
    assert outcome.roadmap.sections["sec_advanced"].subsections["sub_graphs"].prereq_ids == [
        "sub_hashing"
    ]


# --- items ------------------------------------------------------------------


def test_add_item_appends_and_honors_proposed_id() -> None:
    op = AddItemOp(op="add_item", subsection_id="sub_arrays", text="Extra", proposed_id="chk_extra")
    outcome = patch.apply(_draft(), [op])
    arrays = _arrays(outcome.roadmap)
    assert arrays.item_order[-1] == "chk_extra"
    assert arrays.checklist_items["chk_extra"].text == "Extra"


def test_add_item_before_id_positions_within_subsection() -> None:
    arrays_before = _arrays(_draft())
    first_item = arrays_before.item_order[0]
    op = AddItemOp(
        op="add_item",
        subsection_id="sub_arrays",
        text="Very first",
        proposed_id="chk_first",
        before_id=first_item,
    )
    outcome = patch.apply(_draft(), [op])
    assert _arrays(outcome.roadmap).item_order[0] == "chk_first"


def test_update_item_changes_text() -> None:
    item_id = _arrays(_draft()).item_order[0]
    outcome = patch.apply(
        _draft(), [UpdateItemOp(op="update_item", item_id=item_id, text="Redone")]
    )
    assert _arrays(outcome.roadmap).checklist_items[item_id].text == "Redone"


def test_remove_item_drops_it_from_its_subsection() -> None:
    item_id = _arrays(_draft()).item_order[0]
    outcome = patch.apply(_draft(), [RemoveItemOp(op="remove_item", item_id=item_id)])
    assert item_id not in _arrays(outcome.roadmap).checklist_items
    assert item_id not in _arrays(outcome.roadmap).item_order


def test_update_item_unknown_id_names_valid_items() -> None:
    valid_item = _arrays(_draft()).item_order[0]
    with pytest.raises(patch.PatchError) as excinfo:
        patch.apply(_draft(), [UpdateItemOp(op="update_item", item_id="chk_ghost", text="x")])
    assert valid_item in excinfo.value.message


# --- reorder ----------------------------------------------------------------


def test_reorder_a_section() -> None:
    op = ReorderOp(op="reorder", target_id="sec_advanced", before_id="sec_basics")
    outcome = patch.apply(_draft(), [op])
    assert outcome.roadmap.section_order == ["sec_advanced", "sec_basics"]


def test_reorder_a_subsection_within_its_section() -> None:
    op = ReorderOp(op="reorder", target_id="sub_hashing", before_id="sub_arrays")
    outcome = patch.apply(_draft(), [op])
    assert _basics(outcome.roadmap).subsection_order == ["sub_hashing", "sub_arrays"]


def test_reorder_an_item_within_its_subsection() -> None:
    order = _arrays(_draft()).item_order
    op = ReorderOp(op="reorder", target_id=order[1], after_id=order[0])
    outcome = patch.apply(_draft(), [op])
    assert _arrays(outcome.roadmap).item_order == [order[0], order[1]]


def test_reorder_unknown_target_names_reorderable_ids() -> None:
    with pytest.raises(patch.PatchError) as excinfo:
        patch.apply(_draft(), [ReorderOp(op="reorder", target_id="sub_ghost")])
    assert excinfo.value.field == "operations[0].target_id"
    assert "sub_arrays" in excinfo.value.message


def test_reorder_before_a_non_sibling_is_rejected() -> None:
    # A subsection cannot be positioned before a section: they are not siblings.
    op = ReorderOp(op="reorder", target_id="sub_arrays", before_id="sec_advanced")
    with pytest.raises(patch.PatchError) as excinfo:
        patch.apply(_draft(), [op])
    assert excinfo.value.field == "operations[0].before_id"


def test_add_item_after_unknown_sibling_names_valid_items() -> None:
    op = AddItemOp(op="add_item", subsection_id="sub_arrays", text="X", after_id="chk_ghost")
    with pytest.raises(patch.PatchError) as excinfo:
        patch.apply(_draft(), [op])
    assert excinfo.value.field == "operations[0].after_id"


# --- suggested_path ---------------------------------------------------------


def test_set_suggested_path_replaces_the_path() -> None:
    op = SetSuggestedPathOp(
        op="set_suggested_path", path=["sub_graphs", "sub_hashing", "sub_arrays"]
    )
    outcome = patch.apply(_draft(), [op])
    assert outcome.roadmap.suggested_path == ["sub_graphs", "sub_hashing", "sub_arrays"]
    assert outcome.changed_nodes[0].kind is ChangedNodeKind.ROADMAP


# --- intra-batch reference resolution ---------------------------------------


def test_batch_can_reference_a_freshly_added_subsection_by_proposed_id() -> None:
    ops = [
        AddSubsectionOp(
            op="add_subsection",
            section_id="sec_advanced",
            subsection=_sub("Trees", "sub_trees"),
        ),
        AddEdgeOp(op="add_edge", from_id="sub_trees", to_id="sub_graphs"),
    ]
    outcome = patch.apply(_draft(), [*ops])
    graphs = outcome.roadmap.sections["sec_advanced"].subsections["sub_graphs"]
    assert "sub_trees" in graphs.prereq_ids


def test_batch_resolves_a_deduped_proposed_id_in_a_later_op() -> None:
    # Adding a subsection proposing an existing ID de-dupes to sub_arrays-2; a
    # later op referencing sub_arrays-2 must resolve (the remap is applied to
    # references too).
    ops = [
        AddSubsectionOp(
            op="add_subsection",
            section_id="sec_advanced",
            subsection=_sub("Arrays Redux", "sub_arrays"),
        ),
        SetTagsOp(op="set_tags", subsection_id="sub_arrays-2", tags=["redux"]),
    ]
    outcome = patch.apply(_draft(), ops)
    redux = outcome.roadmap.sections["sec_advanced"].subsections["sub_arrays-2"]
    assert redux.tags == ["redux"]


def test_changed_nodes_collapse_repeated_touches_to_one_entry() -> None:
    ops = [
        SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=["a"]),
        SetEffortOp(op="set_effort", subsection_id="sub_arrays", effort_estimate="1h"),
    ]
    outcome = patch.apply(_draft(), ops)
    arrays_changes = [c for c in outcome.changed_nodes if c.id == "sub_arrays"]
    assert len(arrays_changes) == 1
    assert arrays_changes[0].change is ChangeType.UPDATED


# --- property-based ---------------------------------------------------------


@given(texts=st.lists(st.text(min_size=1, max_size=12), min_size=1, max_size=6, unique=True))
def test_add_then_remove_items_round_trips_to_the_original(texts: list[str]) -> None:
    draft = _draft()
    snapshot = draft.model_dump()
    add_ops = [
        AddItemOp(op="add_item", subsection_id="sub_arrays", text=text, proposed_id=f"chk_rt-{i}")
        for i, text in enumerate(texts)
    ]
    added = patch.apply(draft, add_ops)
    minted = [c.id for c in added.changed_nodes if c.kind is ChangedNodeKind.ITEM]
    # Apply the inverse (remove each added item) over the mutated copy.
    removed = patch.apply(
        added.roadmap, [RemoveItemOp(op="remove_item", item_id=i) for i in minted]
    )
    assert removed.roadmap.model_dump() == snapshot


@given(
    tags=st.lists(st.text(min_size=1, max_size=8), max_size=4),
)
def test_set_tags_is_idempotent(tags: list[str]) -> None:
    once = patch.apply(_draft(), [SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=tags)])
    twice = patch.apply(
        once.roadmap, [SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=tags)]
    )
    assert once.roadmap.model_dump() == twice.roadmap.model_dump()


@given(position=st.integers(min_value=0, max_value=3))
def test_one_invalid_op_anywhere_leaves_the_draft_unchanged(position: int) -> None:
    draft = _draft()
    snapshot = draft.model_dump()
    valid: list = [
        SetTagsOp(op="set_tags", subsection_id="sub_arrays", tags=["core"]),
        AddItemOp(op="add_item", subsection_id="sub_hashing", text="x"),
        SetEffortOp(op="set_effort", subsection_id="sub_graphs", effort_estimate="2h"),
    ]
    invalid = UpdateSectionOp(op="update_section", section_id="sec_ghost", title="boom")
    ops = [*valid[:position], invalid, *valid[position:]]
    with pytest.raises(patch.PatchError):
        patch.apply(draft, ops)
    assert draft.model_dump() == snapshot
