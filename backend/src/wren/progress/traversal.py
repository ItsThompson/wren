"""Pure roadmap-traversal helpers shared by the ``next`` and ``summary`` modules.

These are pure functions over the section-04 ``Roadmap`` + ``Progress`` shapes
(no I/O, no framework), so they are testable in isolation and are the composition
seam both derived-read modules build on. Keeping the traversal in one place means
"which items exist" and "which items are checked" are decided once, not
re-derived divergently per projection.
"""

from __future__ import annotations

from wren.progress.schemas import Progress
from wren.roadmaps.schemas import Roadmap, Subsection


def index_subsections(roadmap: Roadmap) -> dict[str, Subsection]:
    """Map every subsection id to its subsection across all sections.

    The DAG spans the whole roadmap (a prereq may live in another section; spec
    section 04), so ``suggested_path`` and ``prereq_ids`` resolve against this
    roadmap-wide index rather than any single section."""
    return {
        sub_id: subsection
        for section in roadmap.sections.values()
        for sub_id, subsection in section.subsections.items()
    }


def all_item_ids(roadmap: Roadmap) -> set[str]:
    """Every checklist-item id defined anywhere in the roadmap.

    Iterates ``item_order`` (the canonical addressable order array), matching the
    counting/done/next helpers so "which items exist" is decided from one source.
    For a published roadmap ``item_order`` and the ``checklist_items`` map agree
    (assembly keeps them in sync); using the order array means an id absent from
    it is uniformly invisible to every derived read. This is the authority for
    which ids are addressable: a ``progress_update`` naming an id outside this set
    is foreign (spec section 06 -> 422), and a stale checked id (from content
    edited before publish) is ignored by the derived reads."""
    return {
        item_id
        for section in roadmap.sections.values()
        for subsection in section.subsections.values()
        for item_id in subsection.item_order
    }


def checked_item_ids(roadmap: Roadmap, progress: Progress) -> set[str]:
    """The set of currently-checked, still-valid item ids.

    Filters the progress map to items that are both checked and still exist in
    the roadmap, so a derived read never counts a stale id."""
    valid = all_item_ids(roadmap)
    return {
        item_id
        for item_id, is_checked in progress.checked.items()
        if is_checked and item_id in valid
    }


def is_subsection_done(subsection: Subsection, checked: set[str]) -> bool:
    """True when every checklist item of ``subsection`` is checked.

    A subsection with no items is vacuously done; published roadmaps require at
    least one item per subsection (V6), so this only bites on drafts."""
    return all(item_id in checked for item_id in subsection.item_order)
