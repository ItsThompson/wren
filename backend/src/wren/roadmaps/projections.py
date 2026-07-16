"""Pure builders for the study-time read projections.

Framework-free functions over the :class:`~wren.roadmaps.schemas.Roadmap`
plus the caller's set of checked checklist-item ids. They build the purpose-built
projections (:class:`Overview`, :class:`NodeDetail`, :class:`SectionPage`,
:class:`SearchHit`) the read endpoints/tools return, keeping "how a projection is
shaped" out of both the transport adapter and the service.

Kept in the roadmaps domain with **no progress-package import**: the caller's
checked set is passed in (resolved by the service via an injected reader), so
these stay pure and independently testable and the dependency arrow stays
progress -> roadmaps, never the reverse. The per-section counting here is a small
domain loop over the roadmap hierarchy, distinct from ``progress.summary`` (which
builds the ``ProgressSnapshot`` wire type in the progress domain)."""

from __future__ import annotations

import base64

from wren.core.read_contract import ResponseFormat
from wren.roadmaps.read_schemas import (
    ItemState,
    NodeDetail,
    OverallProgress,
    Overview,
    PrereqRef,
    ResourceRef,
    SearchHit,
    SearchHitKind,
    SectionInclude,
    SectionOverview,
    SectionPage,
)
from wren.roadmaps.schemas import Roadmap, Section, Subsection


class CursorError(ValueError):
    """A malformed or stale ``SectionPage`` cursor; the service maps it to a 422."""


# ---------- Overview ----------


def build_overview(roadmap: Roadmap, checked: frozenset[str], *, fmt: ResponseFormat) -> Overview:
    """Build the orientation overview: per-section + overall completion counts.

    Sections are emitted in ``section_order`` with no checklist-item bodies.
    ``fmt`` is accepted for uniformity with the rest of the read
    surface (and the MCP ``roadmap_get_overview(format?)`` tool), but the overview
    is already the concise orientation summary: it carries no verbose free-text
    field to trim, so both formats produce the same body."""
    del fmt  # overview has no verbose field to trim; accepted for tool parity
    sections: list[SectionOverview] = []
    total_all = 0
    checked_all = 0
    for section_id in roadmap.section_order:
        section = roadmap.sections.get(section_id)
        if section is None:
            continue
        total, done = _count_section(section, checked)
        sections.append(
            SectionOverview(
                section_id=section_id,
                title=section.title,
                total_items=total,
                checked_items=done,
                percent=_percent(done, total),
            )
        )
        total_all += total
        checked_all += done
    return Overview(
        roadmap_id=roadmap.id,
        title=roadmap.title,
        status=roadmap.status,
        revision=roadmap.revision,
        sections=sections,
        overall=OverallProgress(
            total_items=total_all,
            checked_items=checked_all,
            percent=_percent(checked_all, total_all),
        ),
    )


# ---------- NodeDetail ----------


def build_node_detail(
    roadmap: Roadmap,
    subsection: Subsection,
    checked: frozenset[str],
    *,
    fmt: ResponseFormat = ResponseFormat.CONCISE,
    include: SectionInclude = SectionInclude.BOTH,
) -> NodeDetail:
    """Resolve one subsection into its read projection.

    ``description`` is inlined only in ``detailed`` mode; concise omits it while
    keeping every follow-up ID. ``include`` selects which sub-collections are
    populated: node metadata (tags, effort, resource links, resolved prereqs) for
    ``subsections``/``both``, and the checklist items for ``items``/``both``. The
    ``subsection_id`` and ``title`` are always present so any variant is
    drillable."""
    include_meta = include in (SectionInclude.SUBSECTIONS, SectionInclude.BOTH)
    include_items = include in (SectionInclude.ITEMS, SectionInclude.BOTH)
    detailed = fmt is ResponseFormat.DETAILED
    return NodeDetail(
        subsection_id=subsection.id,
        title=subsection.title,
        description=subsection.description if (detailed and include_meta) else None,
        tags=list(subsection.tags) if include_meta else [],
        effort_estimate=subsection.effort_estimate if include_meta else None,
        resources=_resource_refs(subsection) if include_meta else [],
        prereqs=_prereq_refs(roadmap, subsection, checked) if include_meta else [],
        items=_item_states(subsection, checked) if include_items else [],
    )


def _resource_refs(subsection: Subsection) -> list[ResourceRef]:
    """The subsection's resources as links, in ``resource_order``."""
    refs: list[ResourceRef] = []
    for resource_id in subsection.resource_order:
        resource = subsection.resources.get(resource_id)
        if resource is not None:
            refs.append(
                ResourceRef(
                    id=resource.id, title=resource.title, url=resource.url, type=resource.type
                )
            )
    return refs


def _prereq_refs(
    roadmap: Roadmap, subsection: Subsection, checked: frozenset[str]
) -> list[PrereqRef]:
    """Resolve ``prereq_ids`` to ``{id, title, done}`` against the roadmap-wide index.

    The DAG spans the whole roadmap (a prereq may live in another section), so the
    prereq id resolves against every subsection. ``done`` is ``True`` when all of
    the prerequisite's items are checked. A dangling prereq (only possible on a
    draft; V2 forbids it at publish) resolves to its own id as title and
    ``done=False``."""
    index = _subsection_index(roadmap)
    refs: list[PrereqRef] = []
    for prereq_id in subsection.prereq_ids:
        prereq = index.get(prereq_id)
        if prereq is None:
            refs.append(PrereqRef(id=prereq_id, title=prereq_id, done=False))
            continue
        refs.append(PrereqRef(id=prereq_id, title=prereq.title, done=_is_done(prereq, checked)))
    return refs


def _item_states(subsection: Subsection, checked: frozenset[str]) -> list[ItemState]:
    """The subsection's checklist items in ``item_order``, each with its done state."""
    items: list[ItemState] = []
    for item_id in subsection.item_order:
        item = subsection.checklist_items.get(item_id)
        if item is not None:
            items.append(ItemState(id=item_id, text=item.text, done=item_id in checked))
    return items


# ---------- SectionPage (paginated) ----------


def build_section_page(
    roadmap: Roadmap,
    section: Section,
    cursor: str | None,
    include: SectionInclude,
    checked: frozenset[str],
    *,
    page_size: int,
    fmt: ResponseFormat = ResponseFormat.CONCISE,
) -> SectionPage:
    """Build one page of a section's subsections in ``subsection_order``.

    ``cursor`` is the opaque token from the previous page (``None`` for the first
    page); a malformed or stale cursor raises :class:`CursorError`. When more
    subsections remain, ``next_cursor`` points at the first subsection of the next
    page and ``steering`` reports the truncation. Section nodes default to the
    concise projection (no inlined body): the agent drills into one node with
    ``get_node`` for the full detail."""
    order = section.subsection_order
    start = _decode_cursor(cursor, order) if cursor else 0
    window = order[start : start + page_size]
    nodes = [
        build_node_detail(roadmap, subsection, checked, fmt=fmt, include=include)
        for subsection_id in window
        if (subsection := section.subsections.get(subsection_id)) is not None
    ]
    next_index = start + page_size
    has_more = next_index < len(order)
    next_cursor = _encode_cursor(order[next_index]) if has_more else None
    steering = (
        f"showing {len(window)} of {len(order)}; pass cursor={next_cursor}" if has_more else None
    )
    return SectionPage(
        section_id=section.id,
        title=section.title,
        include=include,
        subsections=nodes,
        next_cursor=next_cursor,
        steering=steering,
    )


def _encode_cursor(subsection_id: str) -> str:
    """Encode the next page's first subsection id as an opaque base64url token."""
    return base64.urlsafe_b64encode(subsection_id.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, order: list[str]) -> int:
    """Resolve an opaque cursor back to its index in ``order``.

    Raises :class:`CursorError` if the token is malformed or points at a
    subsection that is not in this section (a stale or forged cursor), so the
    service can render a 422 rather than silently returning the wrong page."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        subsection_id = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as err:
        raise CursorError("Malformed pagination cursor.") from err
    try:
        return order.index(subsection_id)
    except ValueError as err:
        raise CursorError("Pagination cursor does not match this section.") from err


# ---------- Search ----------


def search(roadmap: Roadmap, query: str | None, tags: list[str] | None) -> list[SearchHit]:
    """Search subsections + items by keyword and/or tag (search, not list-all).

    A keyword (``query``) matches subsection titles and item texts
    (case-insensitive substring); ``tags`` matches subsection track tags
    (case-insensitive). With neither a keyword nor a tag filter the result is
    empty (this is search, never a list-all dump). Hits are emitted in
    ``section_order`` -> ``subsection_order`` -> ``item_order`` and each carries the
    ids needed to drill down."""
    keyword = query.strip().lower() if query else ""
    wanted = {tag.strip().lower() for tag in tags if tag.strip()} if tags else set()
    if not keyword and not wanted:
        return []
    hits: list[SearchHit] = []
    for section_id in roadmap.section_order:
        section = roadmap.sections.get(section_id)
        if section is None:
            continue
        for subsection_id in section.subsection_order:
            subsection = section.subsections.get(subsection_id)
            if subsection is None:
                continue
            _search_subsection(subsection, keyword, wanted, hits)
    return hits


def _search_subsection(
    subsection: Subsection, keyword: str, wanted: set[str], hits: list[SearchHit]
) -> None:
    """Append the subsection hit (title or tag match) and any item-text hits."""
    matched_tags = sorted(tag for tag in subsection.tags if tag.lower() in wanted)
    if (keyword and keyword in subsection.title.lower()) or matched_tags:
        hits.append(
            SearchHit(
                kind=SearchHitKind.SUBSECTION,
                subsection_id=subsection.id,
                title_or_text=subsection.title,
                matched_tags=matched_tags or None,
            )
        )
    if not keyword:
        return
    for item_id in subsection.item_order:
        item = subsection.checklist_items.get(item_id)
        if item is not None and keyword in item.text.lower():
            hits.append(
                SearchHit(
                    kind=SearchHitKind.ITEM,
                    subsection_id=subsection.id,
                    item_id=item_id,
                    title_or_text=item.text,
                )
            )


# ---------- Shared lookups ----------


def find_subsection(roadmap: Roadmap, subsection_id: str) -> Subsection | None:
    """Look up a subsection by id across the whole roadmap (ids are roadmap-wide)."""
    return _subsection_index(roadmap).get(subsection_id)


def all_subsection_ids(roadmap: Roadmap) -> list[str]:
    """Every subsection id in the roadmap, sorted (used to name valid siblings)."""
    return sorted(_subsection_index(roadmap))


def _subsection_index(roadmap: Roadmap) -> dict[str, Subsection]:
    """Map every subsection id to its subsection across all sections."""
    return {
        subsection_id: subsection
        for section in roadmap.sections.values()
        for subsection_id, subsection in section.subsections.items()
    }


def _is_done(subsection: Subsection, checked: frozenset[str]) -> bool:
    """True when every checklist item of ``subsection`` is checked."""
    return all(item_id in checked for item_id in subsection.item_order)


def _count_section(section: Section, checked: frozenset[str]) -> tuple[int, int]:
    """Return ``(total_items, checked_items)`` across a section's subsections."""
    total = 0
    done = 0
    for subsection in section.subsections.values():
        for item_id in subsection.item_order:
            total += 1
            if item_id in checked:
                done += 1
    return total, done


def _percent(done: int, total: int) -> int:
    """Integer completion percent (0..100); 0 for an item-less collection."""
    return round(done / total * 100) if total else 0
