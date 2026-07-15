"""``next``: the pure server-side "what to do next" computation (spec section 05).

Computing next client-side would force the agent to pull the whole
``suggested_path`` + full checked set + every node's ``prereq_ids`` and run a
topological filter in-context (a context blow-up), so the server owns it (spec
section 07 "Why get_next is server-side"). This is a **pure deep module**: it
takes the roadmap + progress and returns the next unchecked, prereq-satisfied
items in ``suggested_path`` order, with a ``complete`` flag when nothing remains.

Minimal by design for this slice: the richer ``why_now`` / ``remaining_in_path``
/ ``path_position`` fields land in Ticket 17, which builds on this.
"""

from __future__ import annotations

from wren.progress.schemas import NextItem, NextResult, Progress, ResourceLink
from wren.progress.traversal import (
    all_item_ids,
    checked_item_ids,
    index_subsections,
    is_subsection_done,
)
from wren.roadmaps.schemas import Roadmap, Subsection


def compute(roadmap: Roadmap, progress: Progress) -> NextResult:
    """Return the next actionable items in ``suggested_path`` order.

    Walks ``suggested_path`` and returns the unchecked items of the first
    subsection that is not yet done and whose prerequisites are all done. When
    every item in the roadmap is checked, ``complete`` is ``True`` and no items
    are returned. When nothing is available (e.g. a draft whose prerequisites are
    unsatisfiable), the item list is empty and ``complete`` is ``False``.
    """
    checked = checked_item_ids(roadmap, progress)
    subsections = index_subsections(roadmap)
    everything_checked = all_item_ids(roadmap) <= checked

    for subsection_id in roadmap.suggested_path:
        subsection = subsections.get(subsection_id)
        if subsection is None:  # id in the path that is not a real node (draft only)
            continue
        if is_subsection_done(subsection, checked):
            continue
        if not _prereqs_done(subsection, subsections, checked):
            continue
        return NextResult(items=_unchecked_items(subsection, checked), complete=False)

    return NextResult(items=[], complete=everything_checked)


def _prereqs_done(
    subsection: Subsection, subsections: dict[str, Subsection], checked: set[str]
) -> bool:
    """True when every prerequisite subsection of ``subsection`` is done.

    A dangling prerequisite (referencing a node that does not exist) can never be
    done, so it holds the dependent back: safe on drafts, and impossible on a
    published roadmap (V2 forbids dangling prereqs)."""
    for prereq_id in subsection.prereq_ids:
        prereq = subsections.get(prereq_id)
        if prereq is None or not is_subsection_done(prereq, checked):
            return False
    return True


def _unchecked_items(subsection: Subsection, checked: set[str]) -> list[NextItem]:
    """The subsection's unchecked items, in ``item_order``, each with its links."""
    links = _resource_links(subsection)
    items: list[NextItem] = []
    for item_id in subsection.item_order:
        if item_id in checked:
            continue
        item = subsection.checklist_items.get(item_id)
        if item is None:  # order array out of sync with the map (defensive)
            continue
        items.append(
            NextItem(
                subsection_id=subsection.id,
                item_id=item_id,
                text=item.text,
                resources=links,
            )
        )
    return items


def _resource_links(subsection: Subsection) -> list[ResourceLink]:
    """The subsection's resources as links, in ``resource_order``."""
    links: list[ResourceLink] = []
    for resource_id in subsection.resource_order:
        resource = subsection.resources.get(resource_id)
        if resource is not None:
            links.append(ResourceLink(title=resource.title, url=resource.url, type=resource.type))
    return links
