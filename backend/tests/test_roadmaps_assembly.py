"""Exhaustive tests for the pure ``assembly`` module.

Verifies the ordered-array -> ID-keyed-map + ``*_order`` transformation, slug
minting per entity, ``proposed_id`` de-dup + remap, and reference resolution
(``prereq_ids`` / ``suggested_path`` from proposed IDs to minted IDs), all without
a database (spec sections 04/13).
"""

from __future__ import annotations

from datetime import UTC, datetime

from wren.roadmaps.assembly import assemble_draft
from wren.roadmaps.schemas import (
    ChecklistItemInput,
    ResourceInput,
    ResourceType,
    RoadmapInput,
    RoadmapStatus,
    SectionInput,
    SubsectionInput,
    Visibility,
)

_NOW = datetime(2026, 7, 15, tzinfo=UTC)


def _sub(
    title: str,
    *,
    proposed_id: str | None = None,
    prereq_ids: list[str] | None = None,
) -> SubsectionInput:
    """A minimal valid subsection input (one resource, one checklist item)."""
    return SubsectionInput(
        proposed_id=proposed_id,
        title=title,
        prereq_ids=prereq_ids or [],
        resources=[ResourceInput(title="Guide", url="https://x.test", type=ResourceType.ARTICLE)],
        checklist_items=[ChecklistItemInput(text="Do it")],
    )


def _assemble(doc: RoadmapInput):
    return assemble_draft(doc, "grokking-dsa-7f3k", owner="user-1", now=_NOW)


def test_assemble_sets_draft_revision_and_owner() -> None:
    result = _assemble(RoadmapInput(title="Grokking DSA"))
    roadmap = result.roadmap
    assert roadmap.id == "grokking-dsa-7f3k"
    assert roadmap.owner == "user-1"
    assert roadmap.status is RoadmapStatus.DRAFT
    assert roadmap.revision == 1
    assert roadmap.visibility is Visibility.PRIVATE
    assert roadmap.created_at == _NOW == roadmap.updated_at


def test_ordered_arrays_become_keyed_maps_plus_order() -> None:
    doc = RoadmapInput(
        title="DSA",
        sections=[
            SectionInput(
                title="Foundations",
                subsections=[_sub("Arrays"), _sub("Hashing")],
            )
        ],
    )
    roadmap = _assemble(doc).roadmap

    assert roadmap.section_order == ["sec_foundations"]
    section = roadmap.sections["sec_foundations"]
    # Map keys are the minted IDs; order array preserves input array order.
    assert section.subsection_order == ["sub_arrays", "sub_hashing"]
    assert set(section.subsections) == {"sub_arrays", "sub_hashing"}
    arrays = section.subsections["sub_arrays"]
    assert arrays.resource_order == list(arrays.resources)
    assert arrays.item_order == list(arrays.checklist_items)
    # Each child entity carries its own minted, prefixed ID.
    assert arrays.resource_order[0].startswith("res_")
    assert arrays.item_order[0].startswith("chk_")


def test_missing_proposed_ids_are_server_minted_from_titles() -> None:
    doc = RoadmapInput(
        title="DSA",
        sections=[SectionInput(title="Graph Theory", subsections=[_sub("Two Pointers")])],
    )
    roadmap = _assemble(doc).roadmap
    assert "sec_graph-theory" in roadmap.sections
    assert "sub_two-pointers" in roadmap.sections["sec_graph-theory"].subsections
    # Nothing was de-duped, so the remap is empty.
    assert _assemble(doc).remap == {}


def test_duplicate_titles_de_dupe_within_the_roadmap() -> None:
    doc = RoadmapInput(
        title="DSA",
        sections=[
            SectionInput(title="Basics", subsections=[_sub("Arrays"), _sub("Arrays")]),
        ],
    )
    section = _assemble(doc).roadmap.sections["sec_basics"]
    assert section.subsection_order == ["sub_arrays", "sub_arrays-2"]


def test_proposed_id_dedup_is_reported_in_the_remap() -> None:
    doc = RoadmapInput(
        title="DSA",
        sections=[
            SectionInput(
                title="Basics",
                subsections=[
                    _sub("Arrays", proposed_id="sub_arrays"),
                    _sub("Arrays again", proposed_id="sub_arrays"),
                ],
            )
        ],
    )
    result = _assemble(doc)
    # The first keeps its proposal; the second is de-duped and remapped.
    assert result.remap == {"sub_arrays": "sub_arrays-2"}
    assert set(result.roadmap.sections["sec_basics"].subsections) == {
        "sub_arrays",
        "sub_arrays-2",
    }


def test_normalization_only_proposal_is_reported_in_the_remap() -> None:
    # A proposal that is merely normalized (no de-dup) still diverges from what
    # the author sent, so it is remapped too (broader than section 04's "de-dup"
    # wording, so references can be reconciled). Here a bare, un-prefixed proposal
    # is normalized to the prefixed minted ID.
    doc = RoadmapInput(
        title="DSA",
        sections=[
            SectionInput(
                title="Basics",
                subsections=[_sub("Two Pointers", proposed_id="two-pointers")],
            )
        ],
    )
    result = _assemble(doc)
    assert result.remap == {"two-pointers": "sub_two-pointers"}
    assert "sub_two-pointers" in result.roadmap.sections["sec_basics"].subsections


def test_exact_proposal_produces_no_remap_entry() -> None:
    # A proposal already in its exact minted form is not remapped.
    doc = RoadmapInput(
        title="DSA",
        sections=[
            SectionInput(
                title="Basics",
                subsections=[_sub("Arrays", proposed_id="sub_arrays")],
            )
        ],
    )
    assert _assemble(doc).remap == {}


def test_prereq_ids_resolve_from_proposed_to_minted_ids() -> None:
    doc = RoadmapInput(
        title="DSA",
        sections=[
            SectionInput(
                title="Basics",
                subsections=[
                    _sub("Arrays", proposed_id="sub_arrays"),
                    _sub("Hashing", proposed_id="sub_hashing", prereq_ids=["sub_arrays"]),
                ],
            )
        ],
    )
    hashing = _assemble(doc).roadmap.sections["sec_basics"].subsections["sub_hashing"]
    assert hashing.prereq_ids == ["sub_arrays"]


def test_prereq_edge_resolves_to_the_kept_proposal_on_duplicate() -> None:
    # When two subsections propose the same ID, the first keeps it and wins the
    # reference mapping; the second is de-duped to a suffixed ID. An edge to the
    # bare handle therefore points at the node that actually kept it.
    doc = RoadmapInput(
        title="DSA",
        sections=[
            SectionInput(
                title="Basics",
                subsections=[
                    _sub("Arrays", proposed_id="sub_x"),
                    _sub("Arrays again", proposed_id="sub_x"),
                ],
            ),
            SectionInput(
                title="Next",
                subsections=[_sub("Sorting", prereq_ids=["sub_x"])],
            ),
        ],
    )
    roadmap = _assemble(doc).roadmap
    sorting = roadmap.sections["sec_next"].subsections["sub_sorting"]
    assert sorting.prereq_ids == ["sub_x"]


def test_suggested_path_resolves_across_sections() -> None:
    doc = RoadmapInput(
        title="DSA",
        suggested_path=["sub_arrays", "sub_graphs"],
        sections=[
            SectionInput(title="A", subsections=[_sub("Arrays", proposed_id="sub_arrays")]),
            SectionInput(title="B", subsections=[_sub("Graphs", proposed_id="sub_graphs")]),
        ],
    )
    roadmap = _assemble(doc).roadmap
    assert roadmap.suggested_path == ["sub_arrays", "sub_graphs"]


def test_unknown_references_pass_through_unchanged() -> None:
    # A reference that matches no proposed_id (e.g. a typo) is left as-is for the
    # publish-time validator to flag; assembly never drops or errors on it.
    doc = RoadmapInput(
        title="DSA",
        suggested_path=["sub_ghost"],
        sections=[SectionInput(title="A", subsections=[_sub("Arrays")])],
    )
    assert _assemble(doc).roadmap.suggested_path == ["sub_ghost"]


def test_forward_reference_to_a_later_subsection_resolves() -> None:
    # prereq points at a subsection declared later in the payload: both passes
    # (mint all, then resolve) make this legal.
    doc = RoadmapInput(
        title="DSA",
        sections=[
            SectionInput(
                title="Basics",
                subsections=[
                    _sub("Arrays", proposed_id="sub_arrays", prereq_ids=["sub_hashing"]),
                    _sub("Hashing", proposed_id="sub_hashing"),
                ],
            )
        ],
    )
    arrays = _assemble(doc).roadmap.sections["sec_basics"].subsections["sub_arrays"]
    assert arrays.prereq_ids == ["sub_hashing"]


def test_subject_tags_and_visibility_are_carried_from_input() -> None:
    doc = RoadmapInput(
        title="DSA",
        subject_tags=["cs", "interview"],
        visibility=Visibility.PUBLIC,
    )
    roadmap = _assemble(doc).roadmap
    assert roadmap.subject_tags == ["cs", "interview"]
    assert roadmap.visibility is Visibility.PUBLIC
