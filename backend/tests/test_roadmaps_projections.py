"""Pure-module tests for the read projections.

The projection builders are pure functions over a ``Roadmap`` + the caller's
checked-item set, so they are tested in isolation without a DB, request, or
token (the high-density layer): every projection shape, the
``concise|detailed`` switch, ``include`` selection, opaque+stable cursor
pagination, and keyword/tag search.
"""

from __future__ import annotations

import base64

import pytest

from roadmaps_read_builders import (
    CHK_ARRAYS_DRILL,
    CHK_ARRAYS_READ,
    CHK_HASH,
    RES_ARRAYS_GUIDE,
    RES_ARRAYS_VIDEO,
    SUB_ARRAYS,
    SUB_GRAPHS,
    SUB_HASHING,
    build_read_roadmap,
)
from wren.core.read_contract import ResponseFormat
from wren.roadmaps import projections
from wren.roadmaps.read_schemas import SearchHitKind, SectionInclude

_ALL_ARRAYS = frozenset({CHK_ARRAYS_READ, CHK_ARRAYS_DRILL})


# --- build_overview ---------------------------------------------------------


def test_overview_lists_sections_in_section_order_with_no_item_bodies() -> None:
    roadmap = build_read_roadmap()
    overview = projections.build_overview(roadmap, frozenset(), fmt=ResponseFormat.CONCISE)
    assert [section.section_id for section in overview.sections] == ["sec_core", "sec_advanced"]
    assert overview.sections[0].title == "Core"
    assert overview.overall.total_items == 4
    # The projection type carries only counts, never checklist-item bodies.
    assert not hasattr(overview.sections[0], "items")


def test_overview_counts_reflect_the_checked_set() -> None:
    roadmap = build_read_roadmap()
    overview = projections.build_overview(
        roadmap, frozenset({CHK_ARRAYS_READ}), fmt=ResponseFormat.CONCISE
    )
    core = next(s for s in overview.sections if s.section_id == "sec_core")
    assert core.total_items == 3  # arrays (2) + hashing (1)
    assert core.checked_items == 1
    assert core.percent == 33
    assert overview.overall.checked_items == 1
    assert overview.overall.percent == 25


def test_overview_all_checked_is_100_percent() -> None:
    roadmap = build_read_roadmap()
    overview = projections.build_overview(
        roadmap,
        frozenset({CHK_ARRAYS_READ, CHK_ARRAYS_DRILL, CHK_HASH, "chk_graphs"}),
        fmt=ResponseFormat.CONCISE,
    )
    assert overview.overall.percent == 100
    assert all(section.percent == 100 for section in overview.sections)


def test_overview_concise_and_detailed_are_identical() -> None:
    # Overview is the orientation summary: it carries no verbose free-text to trim,
    # so the format flag (accepted for tool parity) produces the same body.
    roadmap = build_read_roadmap()
    checked = frozenset({CHK_ARRAYS_READ})
    concise = projections.build_overview(roadmap, checked, fmt=ResponseFormat.CONCISE)
    detailed = projections.build_overview(roadmap, checked, fmt=ResponseFormat.DETAILED)
    assert concise.model_dump() == detailed.model_dump()


# --- build_node_detail ------------------------------------------------------


def test_node_detail_concise_omits_description_but_keeps_follow_up_ids() -> None:
    roadmap = build_read_roadmap()
    arrays = projections.find_subsection(roadmap, SUB_ARRAYS)
    assert arrays is not None
    node = projections.build_node_detail(roadmap, arrays, frozenset(), fmt=ResponseFormat.CONCISE)
    # Concise drops the verbose body...
    assert node.description is None
    # ...but still carries every ID needed for a follow-up call.
    assert node.subsection_id == SUB_ARRAYS
    assert [item.id for item in node.items] == [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL]
    assert [resource.id for resource in node.resources] == [RES_ARRAYS_GUIDE, RES_ARRAYS_VIDEO]
    assert node.tags == ["arrays", "two-pointers"]


def test_node_detail_detailed_includes_description() -> None:
    roadmap = build_read_roadmap()
    arrays = projections.find_subsection(roadmap, SUB_ARRAYS)
    assert arrays is not None
    node = projections.build_node_detail(roadmap, arrays, frozenset(), fmt=ResponseFormat.DETAILED)
    assert node.description == "Two-pointer and sliding-window patterns."


def test_node_detail_concise_is_smaller_than_detailed() -> None:
    # The concise projection is materially leaner (the description is the trimmed
    # free-text), honoring the "~one-third the tokens" contract.
    roadmap = build_read_roadmap()
    arrays = projections.find_subsection(roadmap, SUB_ARRAYS)
    assert arrays is not None
    concise = projections.build_node_detail(
        roadmap, arrays, frozenset(), fmt=ResponseFormat.CONCISE
    )
    detailed = projections.build_node_detail(
        roadmap, arrays, frozenset(), fmt=ResponseFormat.DETAILED
    )
    assert len(concise.model_dump_json()) < len(detailed.model_dump_json())


def test_node_detail_resources_are_links_never_bodies() -> None:
    roadmap = build_read_roadmap()
    arrays = projections.find_subsection(roadmap, SUB_ARRAYS)
    assert arrays is not None
    node = projections.build_node_detail(roadmap, arrays, frozenset(), fmt=ResponseFormat.DETAILED)
    guide = node.resources[0]
    assert guide.url == f"https://x.test/{RES_ARRAYS_GUIDE}"
    assert guide.type.value == "article"
    # A resource carries only the link fields, never inlined article/video content.
    assert set(guide.model_dump()) == {"id", "title", "url", "type"}


def test_node_detail_resolves_prereqs_with_done_state() -> None:
    roadmap = build_read_roadmap()
    hashing = projections.find_subsection(roadmap, SUB_HASHING)
    assert hashing is not None
    # Arrays (the prereq) is fully complete -> done True; its title is resolved.
    node = projections.build_node_detail(roadmap, hashing, _ALL_ARRAYS, fmt=ResponseFormat.CONCISE)
    assert len(node.prereqs) == 1
    assert node.prereqs[0].id == SUB_ARRAYS
    assert node.prereqs[0].title == "Arrays"
    assert node.prereqs[0].done is True


def test_node_detail_prereq_not_done_when_incomplete() -> None:
    roadmap = build_read_roadmap()
    hashing = projections.find_subsection(roadmap, SUB_HASHING)
    assert hashing is not None
    node = projections.build_node_detail(
        roadmap, hashing, frozenset({CHK_ARRAYS_READ}), fmt=ResponseFormat.CONCISE
    )
    assert node.prereqs[0].done is False


def test_node_detail_items_carry_done_state() -> None:
    roadmap = build_read_roadmap()
    arrays = projections.find_subsection(roadmap, SUB_ARRAYS)
    assert arrays is not None
    node = projections.build_node_detail(
        roadmap, arrays, frozenset({CHK_ARRAYS_READ}), fmt=ResponseFormat.CONCISE
    )
    done = {item.id: item.done for item in node.items}
    assert done == {CHK_ARRAYS_READ: True, CHK_ARRAYS_DRILL: False}


def test_node_detail_include_subsections_omits_items() -> None:
    roadmap = build_read_roadmap()
    arrays = projections.find_subsection(roadmap, SUB_ARRAYS)
    assert arrays is not None
    node = projections.build_node_detail(
        roadmap, arrays, frozenset(), include=SectionInclude.SUBSECTIONS
    )
    assert node.items == []
    assert node.resources  # metadata is present
    assert node.tags


def test_node_detail_include_items_omits_metadata() -> None:
    roadmap = build_read_roadmap()
    arrays = projections.find_subsection(roadmap, SUB_ARRAYS)
    assert arrays is not None
    node = projections.build_node_detail(roadmap, arrays, frozenset(), include=SectionInclude.ITEMS)
    assert [item.id for item in node.items] == [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL]
    assert node.resources == []
    assert node.tags == []
    assert node.effort_estimate is None


def test_node_detail_include_both_has_everything() -> None:
    roadmap = build_read_roadmap()
    hashing = projections.find_subsection(roadmap, SUB_HASHING)
    assert hashing is not None
    node = projections.build_node_detail(roadmap, hashing, frozenset(), include=SectionInclude.BOTH)
    assert node.items and node.resources and node.prereqs


def test_node_detail_dangling_prereq_resolves_to_id_and_not_done() -> None:
    # Only possible on a draft (V2 forbids it at publish): a prereq referencing a
    # missing node resolves to its own id as title and done=False (never crashes).
    roadmap = build_read_roadmap()
    hashing = projections.find_subsection(roadmap, SUB_HASHING)
    assert hashing is not None
    dangling = hashing.model_copy(update={"prereq_ids": ["sub_ghost"]})
    node = projections.build_node_detail(roadmap, dangling, frozenset(), fmt=ResponseFormat.CONCISE)
    assert node.prereqs[0].id == "sub_ghost"
    assert node.prereqs[0].title == "sub_ghost"
    assert node.prereqs[0].done is False


# --- build_section_page (pagination) ----------------------------------------


def test_section_page_single_page_has_no_cursor_or_steering() -> None:
    roadmap = build_read_roadmap()
    section = roadmap.sections["sec_core"]
    page = projections.build_section_page(
        roadmap, section, None, SectionInclude.BOTH, frozenset(), page_size=20
    )
    assert [node.subsection_id for node in page.subsections] == [SUB_ARRAYS, SUB_HASHING]
    assert page.next_cursor is None
    assert page.steering is None


def test_section_page_truncates_with_opaque_cursor_and_steering() -> None:
    roadmap = build_read_roadmap()
    section = roadmap.sections["sec_core"]
    page = projections.build_section_page(
        roadmap, section, None, SectionInclude.BOTH, frozenset(), page_size=1
    )
    assert [node.subsection_id for node in page.subsections] == [SUB_ARRAYS]
    assert page.next_cursor is not None
    assert page.steering == f"showing 1 of 2; pass cursor={page.next_cursor}"
    # Opaque: the cursor is base64, not the raw subsection id.
    assert page.next_cursor != SUB_HASHING
    decoded = base64.urlsafe_b64decode(
        page.next_cursor + "=" * (-len(page.next_cursor) % 4)
    ).decode()
    assert decoded == SUB_HASHING


def test_section_page_follows_cursor_to_the_next_page() -> None:
    roadmap = build_read_roadmap()
    section = roadmap.sections["sec_core"]
    first = projections.build_section_page(
        roadmap, section, None, SectionInclude.BOTH, frozenset(), page_size=1
    )
    second = projections.build_section_page(
        roadmap, section, first.next_cursor, SectionInclude.BOTH, frozenset(), page_size=1
    )
    assert [node.subsection_id for node in second.subsections] == [SUB_HASHING]
    assert second.next_cursor is None  # last page


def test_section_page_cursor_is_stable() -> None:
    # The same cursor deterministically returns the same page (stability).
    roadmap = build_read_roadmap()
    section = roadmap.sections["sec_core"]
    cursor = projections.build_section_page(
        roadmap, section, None, SectionInclude.BOTH, frozenset(), page_size=1
    ).next_cursor
    page_a = projections.build_section_page(
        roadmap, section, cursor, SectionInclude.BOTH, frozenset(), page_size=1
    )
    page_b = projections.build_section_page(
        roadmap, section, cursor, SectionInclude.BOTH, frozenset(), page_size=1
    )
    assert page_a.model_dump() == page_b.model_dump()


def test_section_page_malformed_cursor_raises_cursor_error() -> None:
    roadmap = build_read_roadmap()
    section = roadmap.sections["sec_core"]
    with pytest.raises(projections.CursorError):
        projections.build_section_page(
            roadmap, section, "!!not-base64!!", SectionInclude.BOTH, frozenset(), page_size=1
        )


def test_section_page_stale_cursor_for_another_section_raises_cursor_error() -> None:
    roadmap = build_read_roadmap()
    section = roadmap.sections["sec_core"]
    # A well-formed cursor pointing at a subsection not in this section is stale.
    stale = base64.urlsafe_b64encode(SUB_GRAPHS.encode()).decode().rstrip("=")
    with pytest.raises(projections.CursorError):
        projections.build_section_page(
            roadmap, section, stale, SectionInclude.BOTH, frozenset(), page_size=1
        )


def test_section_page_include_propagates_and_nodes_are_concise() -> None:
    roadmap = build_read_roadmap()
    section = roadmap.sections["sec_core"]
    page = projections.build_section_page(
        roadmap, section, None, SectionInclude.ITEMS, frozenset(), page_size=20
    )
    assert page.include is SectionInclude.ITEMS
    # include=items -> items populated, metadata omitted; section nodes are concise.
    assert page.subsections[0].items
    assert page.subsections[0].resources == []
    assert page.subsections[0].description is None


# --- search -----------------------------------------------------------------


def test_search_by_keyword_matches_subsection_title() -> None:
    roadmap = build_read_roadmap()
    hits = projections.search(roadmap, "arrays", None)
    subsection_hits = [h for h in hits if h.kind is SearchHitKind.SUBSECTION]
    assert any(h.subsection_id == SUB_ARRAYS for h in subsection_hits)


def test_search_by_keyword_matches_item_text() -> None:
    roadmap = build_read_roadmap()
    hits = projections.search(roadmap, "hash map", None)
    item_hits = [h for h in hits if h.kind is SearchHitKind.ITEM]
    assert item_hits[0].subsection_id == SUB_HASHING
    assert item_hits[0].item_id == CHK_HASH


def test_search_by_tag_matches_subsection_with_matched_tags() -> None:
    roadmap = build_read_roadmap()
    hits = projections.search(roadmap, None, ["two-pointers"])
    assert len(hits) == 1
    assert hits[0].kind is SearchHitKind.SUBSECTION
    assert hits[0].subsection_id == SUB_ARRAYS
    assert hits[0].matched_tags == ["two-pointers"]


def test_search_is_case_insensitive() -> None:
    roadmap = build_read_roadmap()
    assert projections.search(roadmap, "GRAPHS", None)
    assert projections.search(roadmap, None, ["GRAPHS"])


def test_search_keyword_only_hit_has_no_matched_tags() -> None:
    roadmap = build_read_roadmap()
    hits = projections.search(roadmap, "graphs", None)
    subsection_hit = next(h for h in hits if h.subsection_id == SUB_GRAPHS)
    assert subsection_hit.matched_tags is None


def test_search_without_query_or_tags_is_empty_not_list_all() -> None:
    roadmap = build_read_roadmap()
    assert projections.search(roadmap, None, None) == []
    assert projections.search(roadmap, "", []) == []
    assert projections.search(roadmap, "   ", ["  "]) == []


# --- lookups ----------------------------------------------------------------


def test_find_subsection_and_all_subsection_ids() -> None:
    roadmap = build_read_roadmap()
    assert projections.find_subsection(roadmap, SUB_GRAPHS) is not None
    assert projections.find_subsection(roadmap, "sub_ghost") is None
    assert projections.all_subsection_ids(roadmap) == sorted([SUB_ARRAYS, SUB_HASHING, SUB_GRAPHS])


# --- defensive: order-array / id-map desync (only reachable on a bad draft) --


def test_projections_skip_ids_present_in_order_arrays_but_missing_from_maps() -> None:
    # A malformed roadmap where the *_order arrays name ids absent from their maps
    # (impossible for an assembled/published roadmap) must be skipped, never crash.
    roadmap = build_read_roadmap()
    arrays = roadmap.sections["sec_core"].subsections[SUB_ARRAYS]
    desynced_arrays = arrays.model_copy(
        update={
            "resource_order": [*arrays.resource_order, "res_ghost"],
            "item_order": [*arrays.item_order, "chk_ghost"],
        }
    )
    core = roadmap.sections["sec_core"].model_copy(
        update={
            "subsections": {SUB_ARRAYS: desynced_arrays},
            "subsection_order": [SUB_ARRAYS, "sub_ghost"],
        }
    )
    bad = roadmap.model_copy(
        update={
            "sections": {"sec_core": core},
            "section_order": ["sec_core", "sec_ghost"],
        }
    )
    # Overview skips the missing section (its counts come from the real section's
    # item_order, the addressable-order authority, per traversal/summary).
    overview = projections.build_overview(bad, frozenset(), fmt=ResponseFormat.CONCISE)
    assert [section.section_id for section in overview.sections] == ["sec_core"]
    # NodeDetail skips the ghost resource/item ids (present in the order arrays but
    # absent from the maps).
    node = projections.build_node_detail(bad, desynced_arrays, frozenset())
    assert [resource.id for resource in node.resources] == [RES_ARRAYS_GUIDE, RES_ARRAYS_VIDEO]
    assert [item.id for item in node.items] == [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL]
    # Search skips the missing section + the ghost subsection id (only the real
    # subsection's hits remain).
    assert {hit.subsection_id for hit in projections.search(bad, "arrays", None)} == {SUB_ARRAYS}
