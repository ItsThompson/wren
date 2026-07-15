"""Unit tests for the pure ``progress.summary`` deep module.

``summarize`` is pure over the roadmap + progress, so it is tested in isolation.
Covers per-section + overall counts/percents, the detailed ``checked_ids``
switch, stale-id filtering, and the empty-roadmap edge.
"""

from __future__ import annotations

from datetime import UTC, datetime

from progress_builders import (
    CHK_ARRAYS_DRILL,
    CHK_ARRAYS_READ,
    CHK_HASH,
    build_roadmap,
)
from wren.progress.schemas import Progress
from wren.progress.summary import summarize
from wren.roadmaps.schemas import Roadmap, RoadmapStatus, Visibility

_NOW = datetime(2026, 7, 15, tzinfo=UTC)


def _progress(*checked_ids: str) -> Progress:
    return Progress(
        user_id="learner",
        roadmap_id="grokking-dsa-7f3k",
        checked=dict.fromkeys(checked_ids, True),
        updated_at=_NOW,
    )


def test_counts_overall_and_per_section() -> None:
    # Foundations has 3 items (arrays x2 + hashing x1); Advanced has 1 (graphs).
    snapshot = summarize(
        build_roadmap(), _progress(CHK_ARRAYS_READ, CHK_ARRAYS_DRILL), detailed=False
    )
    assert snapshot.total_items == 4
    assert snapshot.checked_items == 2
    assert snapshot.percent == 50
    by_section = {section.section_id: section for section in snapshot.sections}
    assert by_section["sec_foundations"].total_items == 3
    assert by_section["sec_foundations"].checked_items == 2
    assert by_section["sec_foundations"].percent == 67
    assert by_section["sec_advanced"].checked_items == 0
    assert by_section["sec_advanced"].percent == 0


def test_sections_are_in_section_order() -> None:
    snapshot = summarize(build_roadmap(), _progress(), detailed=False)
    assert [section.section_id for section in snapshot.sections] == [
        "sec_foundations",
        "sec_advanced",
    ]


def test_concise_mode_omits_checked_ids() -> None:
    snapshot = summarize(build_roadmap(), _progress(CHK_HASH), detailed=False)
    assert snapshot.checked_ids is None


def test_detailed_mode_lists_checked_ids_sorted() -> None:
    snapshot = summarize(build_roadmap(), _progress(CHK_ARRAYS_READ, CHK_HASH), detailed=True)
    assert snapshot.checked_ids == sorted([CHK_ARRAYS_READ, CHK_HASH])


def test_stale_checked_id_does_not_inflate_counts() -> None:
    snapshot = summarize(build_roadmap(), _progress(CHK_ARRAYS_READ, "chk_ghost"), detailed=True)
    assert snapshot.checked_items == 1
    assert snapshot.checked_ids == [CHK_ARRAYS_READ]


def test_empty_roadmap_reports_zero_without_dividing_by_zero() -> None:
    empty = Roadmap(
        id="r-0000",
        owner="owner",
        title="Empty",
        visibility=Visibility.PUBLIC,
        status=RoadmapStatus.PUBLISHED,
        revision=1,
        sections={},
        section_order=[],
        suggested_path=[],
        created_at=_NOW,
        updated_at=_NOW,
    )
    snapshot = summarize(empty, _progress(), detailed=False)
    assert snapshot.total_items == 0
    assert snapshot.percent == 0
    assert snapshot.sections == []


def test_section_order_id_missing_from_the_map_is_skipped() -> None:
    # Defensive edge: a section_order id with no backing section is skipped.
    roadmap = build_roadmap()
    desynced = roadmap.model_copy(update={"section_order": [*roadmap.section_order, "sec_ghost"]})
    snapshot = summarize(desynced, _progress(), detailed=False)
    assert [section.section_id for section in snapshot.sections] == [
        "sec_foundations",
        "sec_advanced",
    ]
