"""Shared section-completion counting over a caller's checked-item set.

Single-sources the per-section ``(total, checked)`` tally and the integer
completion percent used by both the roadmaps read projections
(``roadmaps.projections``) and the progress summary (``progress.summary``), so
the two derived reads can never diverge on how completion is computed. The
checked set is accepted as a ``collections.abc.Set`` (imported as ``AbstractSet``)
so a caller may pass either a ``set`` (progress) or a ``frozenset`` (roadmaps)
without adapting: this resolves the annotation drift the two former copies
carried.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Typing-only import: the counting loop is duck-typed over the roadmap
    # hierarchy, so this shared kit carries no runtime dependency on the
    # roadmaps domain (the arrow stays domains -> core, never the reverse).
    from wren.roadmaps.schemas import Section


def count_section(section: Section, checked: AbstractSet[str]) -> tuple[int, int]:
    """Return ``(total_items, checked_items)`` across a section's subsections."""
    total = 0
    done = 0
    for subsection in section.subsections.values():
        for item_id in subsection.item_order:
            total += 1
            if item_id in checked:
                done += 1
    return total, done


def percent(done: int, total: int) -> int:
    """Integer completion percent (0..100); 0 for an item-less collection."""
    return round(done / total * 100) if total else 0
