"""RoadmapReadService: study-time reads, isolated from authoring/lifecycle.

The narrow read surface behind ``GET /roadmaps/{id}`` and the four read
projections (overview / node / paginated section / search). It is a **separate
service** from :class:`~wren.roadmaps.service.RoadmapService` (authoring +
lifecycle), mirroring the :class:`~wren.roadmaps.listing.ListingService`
precedent: reads are a distinct concern with their own readability guards and a
cross-domain progress dependency the authoring service does not share.

It receives the same narrow :data:`CheckedReader` callable the authoring service
used to get from ``roadmaps/wiring.py`` (the progress repository adapted to a
``Callable``), preserving the one-way roadmaps -> (narrow callable) <- progress
decoupling: the roadmaps domain never imports the progress repository into its
own logic.

The readability rule (own-or-public, drafts non-discoverable, 404-over-403 with
no existence leak) lives here as the module-level :func:`load_readable` free
function so the single copy is shared with :meth:`RoadmapService.fork` (which
forks any *readable* source) without duplicating a guard into both services.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from wren.core.errors import NotFound, Validation
from wren.core.observability import track_failures
from wren.roadmaps import projections
from wren.roadmaps.config import SECTION_PAGE_SIZE
from wren.roadmaps.schemas import Roadmap, RoadmapStatus, Visibility

if TYPE_CHECKING:
    from wren.core.read_contract import ResponseFormat
    from wren.roadmaps.read_schemas import (
        NodeDetail,
        Overview,
        SearchHit,
        SectionInclude,
        SectionPage,
    )
    from wren.roadmaps.repository import RoadmapRepository

# How a read learns the caller's checked checklist-item ids for the progress-aware
# projections (Overview counts, NodeDetail done-state). A narrow injected callable
# rather than the progress repository, so the roadmaps domain stays decoupled from
# the progress domain (the wiring binds it to the progress repository; tests
# substitute a closure over a seeded set).
CheckedReader = Callable[[str, str], Awaitable[frozenset[str]]]


async def _no_checked_items(_user_id: str, _roadmap_id: str) -> frozenset[str]:
    """Default checked reader: no progress (every item un-done).

    Production wiring binds the real progress-backed reader; this default keeps the
    read projections usable in unit/contract tests that do not seed progress."""
    return frozenset()


async def load_readable(repo: RoadmapRepository, user_id: str, roadmap_id: str) -> Roadmap:
    """Load a roadmap the caller may **read**: their own (any status) or a public
    one.

    Readability first: a private roadmap owned by someone else is a 404 that leaks
    no existence, matching the progress readability convention. Backs both the
    read service's :meth:`RoadmapReadService._load_readable` and
    :meth:`RoadmapService.fork` (the fork source must be readable) from one place,
    so the own-or-public rule is single-sourced rather than duplicated into both
    services. Unlike the progress readability check it does not require
    ``published`` status, so a caller can fork or preview their own draft as well
    as any public roadmap. Uses the unscoped repository read (a read/fork source is
    not owner-scoped), then applies the readability rule here.
    """
    record = await repo.get(roadmap_id)
    if record is None:
        raise NotFound(f"No roadmap '{roadmap_id}'.", instance=f"/roadmaps/{roadmap_id}")
    roadmap = Roadmap.model_validate(record.document)
    if roadmap.owner != user_id and roadmap.visibility is not Visibility.PUBLIC:
        # Private roadmap owned by someone else: 404, no existence leak.
        raise NotFound(f"No roadmap '{roadmap_id}'.", instance=f"/roadmaps/{roadmap_id}")
    return roadmap


@track_failures("roadmaps")
class RoadmapReadService:
    """Study-time reads for roadmaps, isolated from authoring/lifecycle."""

    def __init__(
        self,
        repo: RoadmapRepository,
        *,
        checked_reader: CheckedReader = _no_checked_items,
        section_page_size: int = SECTION_PAGE_SIZE,
    ) -> None:
        self._repo = repo
        # Resolves the caller's checked item ids for the progress-aware read
        # projections (Overview counts, NodeDetail done-state); injected so the
        # roadmaps domain never imports the progress repository into its own logic.
        self._checked_reader = checked_reader
        # Server-set section page size; injected so a test
        # can force truncation on a small fixture.
        self._section_page_size = section_page_size

    async def get(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Return the full roadmap to a caller who may read it (owner draft preview
        or readable published).

        The owner reads their own roadmap at any status (draft preview included); a
        non-owner may read a **public** roadmap that is published or archived (by
        direct link). A private roadmap owned by someone else, or a non-owner's
        request for a public *draft* (not discoverable), is a 404 with no existence
        leak. This is the read that backs the public list view / profile.
        """
        return await self._load_readable_document(user_id, roadmap_id)

    async def get_overview(self, user_id: str, roadmap_id: str, fmt: ResponseFormat) -> Overview:
        """Orientation overview: sections in ``section_order`` with per-section and
        overall completion counts, no checklist-item bodies.

        Readable by the owner (any non-draft or their own draft) or a non-owner on
        a public published/archived roadmap; the counts reflect the **caller's**
        progress (zero when they have not started)."""
        roadmap = await self._load_readable_document(user_id, roadmap_id)
        checked = await self._checked_reader(user_id, roadmap_id)
        return projections.build_overview(roadmap, checked, fmt=fmt)

    async def get_node(
        self, user_id: str, roadmap_id: str, subsection_id: str, fmt: ResponseFormat
    ) -> NodeDetail:
        """One subsection resolved for study: description (detailed only), tags,
        resource links, ``prereq_ids`` resolved to ``{id,title,done}``, and items
        ``{id,text,done}``.

        An unknown subsection id is a 404 that names the valid sibling subsection
        ids so the agent can self-correct. Done-state is the caller's own."""
        roadmap = await self._load_readable_document(user_id, roadmap_id)
        subsection = projections.find_subsection(roadmap, subsection_id)
        if subsection is None:
            siblings = ", ".join(projections.all_subsection_ids(roadmap)) or "none"
            raise NotFound(
                f"No subsection '{subsection_id}' in roadmap '{roadmap_id}'. "
                f"Valid subsections: {siblings}.",
                instance=f"/roadmaps/{roadmap_id}/nodes/{subsection_id}",
            )
        checked = await self._checked_reader(user_id, roadmap_id)
        return projections.build_node_detail(roadmap, subsection, checked, fmt=fmt)

    async def get_section(
        self,
        user_id: str,
        roadmap_id: str,
        section_id: str,
        cursor: str | None,
        include: SectionInclude,
    ) -> SectionPage:
        """Paginated section drill-down.

        Returns a ``SectionPage`` of the section's subsections in
        ``subsection_order`` with a server-set page size, an opaque ``next_cursor``
        (absent on the last page), and steering text when truncated. ``include``
        selects node metadata, items, or both. An unknown section id is a 404
        naming the valid sections; a malformed/stale cursor is a 422."""
        roadmap = await self._load_readable_document(user_id, roadmap_id)
        section = roadmap.sections.get(section_id)
        if section is None:
            siblings = ", ".join(roadmap.section_order) or "none"
            raise NotFound(
                f"No section '{section_id}' in roadmap '{roadmap_id}'. Valid sections: {siblings}.",
                instance=f"/roadmaps/{roadmap_id}/sections/{section_id}",
            )
        checked = await self._checked_reader(user_id, roadmap_id)
        try:
            return projections.build_section_page(
                roadmap, section, cursor, include, checked, page_size=self._section_page_size
            )
        except projections.CursorError as err:
            raise Validation(
                str(err),
                fields={"cursor": str(err)},
                instance=f"/roadmaps/{roadmap_id}/sections/{section_id}",
            ) from err

    async def search(
        self, user_id: str, roadmap_id: str, query: str | None, tags: list[str] | None
    ) -> list[SearchHit]:
        """Search the roadmap's subsections + items by keyword and/or tag: search,
        not list-all (empty query and no tags -> ``[]``).

        Each hit carries the ids needed to drill down. Needs no progress, so it is
        a pure projection over the readable roadmap."""
        roadmap = await self._load_readable_document(user_id, roadmap_id)
        return projections.search(roadmap, query, tags)

    async def _load_readable(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Load a roadmap the caller may read (own-or-public), delegating to the
        single-sourced :func:`load_readable` rule.

        Kept as the read service's named readable guard so
        :meth:`_load_readable_document` layers on it cleanly; the shared free
        function is what lets :meth:`RoadmapService.fork` reuse the same rule
        without duplicating a guard into both services.
        """
        return await load_readable(self._repo, user_id, roadmap_id)

    async def _load_readable_document(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Load a roadmap the caller may read as a study-time reader (owner draft
        preview or readable published).

        Builds on :meth:`_load_readable` (own-or-public; a private roadmap owned by
        someone else is a 404 with no existence leak) and layers the reader status
        gate on top: a non-owner may read a **public** roadmap only when it is
        published or archived (readable by direct link), never a public *draft*
        (drafts are not discoverable), which is a 404 with no existence leak. The
        owner still reads their own roadmap at any status (draft preview). This is
        the shared load under ``get`` and every read projection.
        """
        roadmap = await self._load_readable(user_id, roadmap_id)
        if roadmap.owner != user_id and roadmap.status is RoadmapStatus.DRAFT:
            # A non-owner cannot read another user's draft even if it is public
            # (drafts are not discoverable): 404, no existence leak.
            raise NotFound(f"No roadmap '{roadmap_id}'.", instance=f"/roadmaps/{roadmap_id}")
        return roadmap
