"""``next``: the pure server-side "what to do next" computation.

Computing next client-side would force the agent to pull the whole
``suggested_path`` + full checked set + every node's ``prereq_ids`` and run a
topological filter in-context (a context blow-up), so the server owns it. This is
a **pure deep module**: it
takes the roadmap + progress and returns the next unchecked, prereq-satisfied
items in ``suggested_path`` order, each with a structural ``why_now`` and its
resource links, plus a ``remaining_in_path`` count and a ``complete`` flag.

The ``why_now`` rationale is STRUCTURAL only: the item is the
next unchecked one in ``suggested_path`` and its named prerequisites are
complete. It never contains pedagogical / ZPD reasoning: that intelligence lives
in the agent and was baked into ``suggested_path`` at authoring time, which
guards the load-bearing thesis that the app is not the brain.
"""

from __future__ import annotations

from wren.progress.schemas import NextItem, NextResult, Progress, ResourceLink
from wren.progress.traversal import (
    all_item_ids,
    checked_item_ids,
    index_subsections,
    is_subsection_done,
)
from wren.roadmaps.read_schemas import ResponseFormat
from wren.roadmaps.schemas import Roadmap, Subsection


def compute(
    roadmap: Roadmap,
    progress: Progress,
    *,
    fmt: ResponseFormat = ResponseFormat.CONCISE,
) -> NextResult:
    """Return the next actionable items in ``suggested_path`` order.

    Walks ``suggested_path`` and returns the unchecked items of the first
    subsection that is not yet done and whose prerequisites are all done, each
    carrying a structural ``why_now`` and its resource links. ``remaining_in_path``
    counts the subsections still to do along the path. When every item in the
    roadmap is checked, ``complete`` is ``True`` and no items are returned. When
    nothing is available (e.g. a draft whose prerequisites are unsatisfiable), the
    item list is empty and ``complete`` is ``False``. ``path_position`` (the
    1-based index of the returned subsection in ``suggested_path``) is attached
    only in ``detailed`` mode.
    """
    checked = checked_item_ids(roadmap, progress)
    subsections = index_subsections(roadmap)
    everything_checked = all_item_ids(roadmap) <= checked
    detailed = fmt is ResponseFormat.DETAILED
    remaining = _remaining_in_path(roadmap, subsections, checked)

    for position, subsection_id in enumerate(roadmap.suggested_path, start=1):
        subsection = subsections.get(subsection_id)
        if subsection is None:  # id in the path that is not a real node (draft only)
            continue
        if is_subsection_done(subsection, checked):
            continue
        if not _prereqs_done(subsection, subsections, checked):
            continue
        items = _unchecked_items(subsection, checked, path_position=position if detailed else None)
        return NextResult(items=items, remaining_in_path=remaining, complete=False)

    return NextResult(items=[], remaining_in_path=remaining, complete=everything_checked)


def _remaining_in_path(
    roadmap: Roadmap, subsections: dict[str, Subsection], checked: set[str]
) -> int:
    """Count the subsections in ``suggested_path`` still to do (not yet done).

    A path id that is not a real node (draft only) is skipped; an item-less
    subsection is vacuously done and so does not count. On a published roadmap
    ``suggested_path`` covers every subsection exactly once (V3), so this is the
    count of subsections with at least one unchecked item."""
    return sum(
        1
        for subsection_id in roadmap.suggested_path
        if (subsection := subsections.get(subsection_id)) is not None
        and not is_subsection_done(subsection, checked)
    )


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


def _unchecked_items(
    subsection: Subsection, checked: set[str], *, path_position: int | None
) -> list[NextItem]:
    """The subsection's unchecked items, in ``item_order``, each with its links.

    Every item of the returned subsection shares the same structural ``why_now``
    and ``path_position`` (both are properties of the subsection's place in the
    path, not the individual item)."""
    links = _resource_links(subsection)
    why_now = _why_now(subsection)
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
                why_now=why_now,
                resources=links,
                path_position=path_position,
            )
        )
    return items


def _why_now(subsection: Subsection) -> str:
    """The STRUCTURAL rationale for surfacing this subsection now.

    States only mechanical facts the app owns: this is the next unchecked
    subsection in ``suggested_path`` and its named prerequisites are complete.
    Never pedagogical / ZPD judgement (no difficulty, readiness, or effort claim):
    that intelligence lives in the agent, which guards the thesis that the app is
    not the brain."""
    if subsection.prereq_ids:
        prereqs = ", ".join(subsection.prereq_ids)
        return (
            f"Next unchecked subsection in the suggested path; "
            f"prerequisites {prereqs} are complete."
        )
    return "Next unchecked subsection in the suggested path; it has no prerequisites."


def _resource_links(subsection: Subsection) -> list[ResourceLink]:
    """The subsection's resources as links, in ``resource_order``."""
    links: list[ResourceLink] = []
    for resource_id in subsection.resource_order:
        resource = subsection.resources.get(resource_id)
        if resource is not None:
            links.append(ResourceLink(title=resource.title, url=resource.url, type=resource.type))
    return links
