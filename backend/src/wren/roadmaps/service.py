"""RoadmapService: draft authoring.

The single source of truth for roadmap business rules. It receives a repository
and the resolved ``user_id`` (never trusted from payload), composes the pure
``slugs``/``assembly`` deep modules, raises ``WrenError`` subclasses for the
adapter to render, and owns the transaction boundary (``get_session`` is
yield-only).

This slice implements ``create_draft``, the owner-scoped ``get``, the iterative
``patch_draft``, the full-document ``replace_draft`` import escape hatch, the
minimal ``validate`` / ``publish`` lifecycle (the draft -> published one-way
transition that makes content immutable), ``fork`` (a new draft seeded from any
readable roadmap), ``edit_metadata`` (the sanctioned presentation-only edit
that stays allowed post-publish), and the web-only lifecycle actions
``set_visibility`` / ``archive`` / ``delete`` (delete guarded by a zero-followers
check; archive the safe retirement path). The read projections are later slices;
the full structural contract composes onto ``validate`` in a later slice.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from wren.core.errors import Conflict, ErrorCode, NotFound, Validation, Violation
from wren.core.logging import get_logger
from wren.core.observability import track_failures
from wren.roadmaps import patch, projections, slugs
from wren.roadmaps.assembly import assemble_draft, assemble_fork
from wren.roadmaps.config import MAX_ID_MINT_ATTEMPTS, SECTION_PAGE_SIZE
from wren.roadmaps.models import RoadmapRecord
from wren.roadmaps.read_schemas import (
    NodeDetail,
    Overview,
    ResponseFormat,
    SearchHit,
    SectionInclude,
    SectionPage,
)
from wren.roadmaps.repository import RoadmapRepository
from wren.roadmaps.schemas import (
    PatchOp,
    PatchResult,
    Roadmap,
    RoadmapCreated,
    RoadmapInput,
    RoadmapReplaced,
    RoadmapStatus,
    Visibility,
)
from wren.roadmaps.validation import validate_structure

_log = get_logger("wren-roadmaps")

TokenFactory = Callable[[], str]
Clock = Callable[[], datetime]
# How the service learns a roadmap's follower count for the delete guard. A narrow
# injected callable (not the whole progress repository) keeps the roadmaps domain
# decoupled from the progress domain: the wiring binds it to the progress
# repository's indexed count, tests substitute a constant.
FollowerCounter = Callable[[str], Awaitable[int]]
# How a read learns the caller's checked checklist-item ids for the progress-aware
# projections (Overview counts, NodeDetail done-state). Like FollowerCounter, a
# narrow injected callable rather than the progress repository, so the roadmaps
# domain stays decoupled from the progress domain (the wiring binds it to the
# progress repository; tests substitute a closure over a seeded set).
CheckedReader = Callable[[str, str], Awaitable[frozenset[str]]]


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _no_checked_items(_user_id: str, _roadmap_id: str) -> frozenset[str]:
    """Default checked reader: no progress (every item un-done).

    Production wiring binds the real progress-backed reader; this default keeps the
    read projections usable in unit/contract tests that do not seed progress."""
    return frozenset()


@track_failures("roadmaps")
class RoadmapService:
    """Business rules for authoring roadmap drafts."""

    def __init__(
        self,
        repo: RoadmapRepository,
        *,
        follower_counter: FollowerCounter,
        checked_reader: CheckedReader = _no_checked_items,
        token_factory: TokenFactory = slugs.random_token,
        clock: Clock = _utcnow,
        section_page_size: int = SECTION_PAGE_SIZE,
    ) -> None:
        self._repo = repo
        # Counts followers for the delete guard; injected so the roadmaps domain
        # never imports the progress repository (the wiring composes them).
        self._follower_counter = follower_counter
        # Resolves the caller's checked item ids for the progress-aware read
        # projections (Overview counts, NodeDetail done-state); injected the same
        # way as the follower counter so roadmaps stays decoupled from progress.
        self._checked_reader = checked_reader
        # The random-token source and clock are injected so tests can force an
        # ID collision (re-roll) and pin timestamps without patching globals.
        self._token_factory = token_factory
        self._clock = clock
        # Server-set section page size; injected so a test
        # can force truncation on a small fixture.
        self._section_page_size = section_page_size

    async def create_draft(self, user_id: str, doc: RoadmapInput) -> RoadmapCreated:
        """Mint slug IDs, resolve references, and persist a private draft.

        Returns the full roadmap at ``revision`` 1 plus the ``proposed_id ->
        minted_id`` remap for any de-duped proposal.
        """
        roadmap_id = await self._mint_unique_roadmap_id(doc.proposed_id or doc.title)
        assembled = assemble_draft(doc, roadmap_id, owner=user_id, now=self._clock())
        try:
            await self._repo.add(_to_record(assembled.roadmap))
            await self._repo.commit()
        except Exception:
            await self._repo.rollback()
            raise
        _log.info("roadmap_draft_created", roadmap_id=roadmap_id, owner=user_id)
        return RoadmapCreated.model_validate(
            {**assembled.roadmap.model_dump(), "remap": assembled.remap}
        )

    async def patch_draft(
        self, user_id: str, roadmap_id: str, revision: int, operations: list[PatchOp]
    ) -> PatchResult:
        """Apply an atomic op batch to the caller's draft under optimistic
        concurrency.

        Loads through the shared content-write guard (:meth:`_load_writable_draft`:
        404 for a non-owner / unknown ID, 409 ``IMMUTABLE`` on a published or
        archived roadmap), then rejects a stale ``If-Match`` ``revision`` with a 409
        "re-read". :func:`patch.apply` is all-or-nothing: an invalid op raises and
        nothing is persisted; on success the ``revision`` bumps by one and only the
        changed nodes (plus any de-dup remap) are echoed.
        """
        draft = await self._load_writable_draft(user_id, roadmap_id)
        if draft.revision != revision:
            raise Conflict(
                f"Your edit targeted revision {revision} but the current revision is "
                f"{draft.revision}. Re-read and retry.",
                code=ErrorCode.STALE_REVISION,
                instance=f"/roadmaps/{roadmap_id}",
            )
        try:
            outcome = patch.apply(draft, operations)
        except patch.PatchError as err:
            # A model-recoverable op failure (unknown ID naming valid siblings, or
            # a cycle-creating edge explaining the cycle) -> field-level 422.
            raise Validation(
                err.message,
                fields={err.field: err.message},
                instance=f"/roadmaps/{roadmap_id}",
            ) from err
        patched = outcome.roadmap.model_copy(
            update={"revision": draft.revision + 1, "updated_at": self._clock()}
        )
        try:
            await self._repo.save(patched)
            await self._repo.commit()
        except Exception:
            await self._repo.rollback()
            raise
        _log.info(
            "roadmap_patched",
            roadmap_id=roadmap_id,
            owner=user_id,
            revision=patched.revision,
            ops=len(operations),
        )
        return PatchResult(
            roadmap_id=roadmap_id,
            revision=patched.revision,
            changed_nodes=outcome.changed_nodes,
            remap=outcome.remap,
        )

    async def replace_draft(
        self, user_id: str, roadmap_id: str, revision: int, doc: RoadmapInput
    ) -> RoadmapReplaced:
        """Replace the caller's entire draft from a full ``RoadmapInput``.

        The documented **import escape hatch**, never the iterative path: it rebuilds
        the whole document rather than editing in place. Loads through the same
        content-write guard as :meth:`patch_draft` (:meth:`_load_writable_draft`: 404
        for a non-owner / unknown ID, 409 ``IMMUTABLE`` on a published/archived
        roadmap) and is guarded by the same optimistic-concurrency ``If-Match``
        ``revision`` (stale -> 409 "re-read"), because a full replace is a
        structure-mutating write.

        ID semantics: the roadmap's own ID (the route param)
        is unchanged, nodes carrying a ``proposed_id`` keep it, and every other node
        is re-minted, all via the shared :func:`assemble_draft` mint-then-resolve
        pass. ``created_at``, ``owner``, and ``visibility`` are preserved; ``revision``
        bumps by one and the ``proposed_id -> minted_id`` remap is returned so the
        author can reconcile any de-duped reference.

        Visibility is deliberately taken from the **stored** draft, not the imported
        document: a full-document import replaces content, so it must not silently
        flip a draft public/private. Visibility is a web-only lifecycle toggle,
        changed only through :meth:`set_visibility`.
        """
        draft = await self._load_writable_draft(user_id, roadmap_id)
        if draft.revision != revision:
            raise Conflict(
                f"Your import targeted revision {revision} but the current revision is "
                f"{draft.revision}. Re-read and retry.",
                code=ErrorCode.STALE_REVISION,
                instance=f"/roadmaps/{roadmap_id}",
            )
        # Rebuild from the full document using the same pure assembly as create: the
        # roadmap ID is the (unchanged) route param, so no re-mint/collision check is
        # needed. Preserve created_at + bump the revision (assemble_draft resets both).
        assembled = assemble_draft(doc, roadmap_id, owner=user_id, now=self._clock())
        replaced = assembled.roadmap.model_copy(
            update={
                "revision": draft.revision + 1,
                "created_at": draft.created_at,
                "visibility": draft.visibility,
            }
        )
        try:
            await self._repo.save(replaced)
            await self._repo.commit()
        except Exception:
            await self._repo.rollback()
            raise
        _log.info(
            "roadmap_replaced",
            roadmap_id=roadmap_id,
            owner=user_id,
            revision=replaced.revision,
        )
        return RoadmapReplaced.model_validate({**replaced.model_dump(), "remap": assembled.remap})

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

    async def validate(self, user_id: str, roadmap_id: str) -> list[Violation]:
        """Run the structural checks on the caller's own draft and return every
        violation in one pass (possibly empty). Never mutates; drafts only (a
        published/archived roadmap raises ``Conflict``)."""
        draft = await self._load_owned_draft(user_id, roadmap_id)
        return validate_structure(draft)

    async def publish(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Validate then transition the caller's draft ``draft -> published``.

        Hard-block: any structural violation raises ``Validation`` (422) and the
        roadmap stays ``draft``. Publish is one-way and makes the content
        immutable (structural writes on a non-draft are refused by the same
        :meth:`_load_owned_draft` guard).
        """
        draft = await self._load_owned_draft(user_id, roadmap_id)
        violations = validate_structure(draft)
        if violations:
            rules = "rule" if len(violations) == 1 else "rules"
            raise Validation(
                f"{len(violations)} structural {rules} failed.",
                violations=violations,
                instance=f"/roadmaps/{roadmap_id}",
            )
        published = draft.model_copy(
            update={"status": RoadmapStatus.PUBLISHED, "updated_at": self._clock()}
        )
        try:
            await self._repo.save(published)
            await self._repo.commit()
        except Exception:
            await self._repo.rollback()
            raise
        _log.info("roadmap_published", roadmap_id=roadmap_id, owner=user_id)
        return published

    async def fork(self, user_id: str, source_roadmap_id: str) -> Roadmap:
        """Seed a brand-new draft from any roadmap the caller may read.

        Readable means the caller's own roadmap (any status) or a public one; a
        private roadmap owned by someone else is a 404 with no existence leak
        (:meth:`_load_readable`). The fork is a faithful content copy under a
        freshly-minted, globally-unique roadmap ID (never derived from the source),
        owned by the forking user, reset to a private ``draft`` at ``revision`` 1.
        No progress is carried over: fork creates no progress record, so the forker
        starts the copy with a clean slate. The source is never
        mutated (the copy is a fresh insert).
        """
        source = await self._load_readable(user_id, source_roadmap_id)
        new_id = await self._mint_unique_roadmap_id(source.title)
        forked = assemble_fork(source, new_id, owner=user_id, now=self._clock())
        try:
            await self._repo.add(_to_record(forked))
            await self._repo.commit()
        except Exception:
            await self._repo.rollback()
            raise
        _log.info(
            "roadmap_forked",
            roadmap_id=new_id,
            source_roadmap_id=source_roadmap_id,
            owner=user_id,
        )
        return forked

    async def edit_metadata(
        self,
        user_id: str,
        roadmap_id: str,
        title: str | None,
        description: str | None,
        subject_tags: list[str] | None,
    ) -> Roadmap:
        """Edit the presentation-only fields on the caller's own roadmap.

        ``title`` / ``description`` / ``subject_tags`` stay mutable after publish
        (they touch no follower-visible structure), so this loads through the plain
        owner guard (:meth:`_load_owned`), **not** the content-write immutability
        guard: a published roadmap is edited here while structural writes on it stay
        409. It is deliberately not ``If-Match``-guarded and does not bump the
        structural ``revision`` (last-write-wins). Only fields
        explicitly provided (not ``None``) are changed; ``visibility``, ``status``,
        and all content are untouched (a smuggled structural field is rejected at
        the wire boundary by :meth:`MetadataEditRequest.reject_structural_fields`).
        """
        roadmap = await self._load_owned(user_id, roadmap_id)
        updates: dict[str, object] = {"updated_at": self._clock()}
        if title is not None:
            updates["title"] = title
        if description is not None:
            updates["description"] = description
        if subject_tags is not None:
            updates["subject_tags"] = list(subject_tags)
        edited = roadmap.model_copy(update=updates)
        try:
            await self._repo.save(edited)
            await self._repo.commit()
        except Exception:
            await self._repo.rollback()
            raise
        _log.info("roadmap_metadata_edited", roadmap_id=roadmap_id, owner=user_id)
        return edited

    async def set_visibility(
        self, user_id: str, roadmap_id: str, visibility: Visibility
    ) -> Roadmap:
        """Toggle the caller's own roadmap public/private (web-only).

        Loads through the plain owner guard (:meth:`_load_owned`), so it applies to
        a roadmap of any status (a draft or a published one): visibility is a
        lifecycle field, not follower-visible structure. A public roadmap is
        reachable by link and appears on the owner's profile; a private one is
        owner-only. Last-write-wins (deliberately not ``If-Match``-guarded) and it
        never bumps the structural ``revision`` or alters any content. Setting the
        current value again is an idempotent no-op beyond the timestamp.
        """
        roadmap = await self._load_owned(user_id, roadmap_id)
        updated = roadmap.model_copy(update={"visibility": visibility, "updated_at": self._clock()})
        try:
            await self._repo.save(updated)
            await self._repo.commit()
        except Exception:
            await self._repo.rollback()
            raise
        _log.info(
            "roadmap_visibility_set",
            roadmap_id=roadmap_id,
            owner=user_id,
            visibility=visibility.value,
        )
        return updated

    async def archive(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Archive the caller's own published roadmap (web-only).

        Archive is the safe retirement path (the alternative offered when a delete
        is blocked by followers): it hides the roadmap from discovery (the owner's
        profile) while existing followers keep it and their progress. Only a
        ``published`` roadmap can be archived (the ``draft -> published -> archived``
        lifecycle is linear); a draft (delete it instead) or an already-archived
        roadmap raises ``Conflict``. Archiving alters no content and keeps the
        structural ``revision``.
        """
        roadmap = await self._load_owned(user_id, roadmap_id)
        if roadmap.status is not RoadmapStatus.PUBLISHED:
            raise Conflict(
                f"Roadmap '{roadmap_id}' is {roadmap.status.value}; only a published roadmap can "
                "be archived.",
                instance=f"/roadmaps/{roadmap_id}",
            )
        archived = roadmap.model_copy(
            update={"status": RoadmapStatus.ARCHIVED, "updated_at": self._clock()}
        )
        try:
            await self._repo.save(archived)
            await self._repo.commit()
        except Exception:
            await self._repo.rollback()
            raise
        _log.info("roadmap_archived", roadmap_id=roadmap_id, owner=user_id)
        return archived

    async def delete(self, user_id: str, roadmap_id: str) -> None:
        """Delete the caller's own roadmap, but only when it has zero followers
        (web-only).

        Loads through the plain owner guard (:meth:`_load_owned`: a non-owner /
        unknown ID is a 404 with no existence leak), then counts followers via the
        injected :attr:`_follower_counter`. With any follower the delete is refused
        with a 409 ``DELETE_HAS_FOLLOWERS`` steering the caller to ``archive``
        instead (which retires the roadmap while followers keep their progress);
        with zero followers the row is removed. Applies to a roadmap of any status
        (a draft always has zero followers, since a draft is not followable).
        """
        roadmap = await self._load_owned(user_id, roadmap_id)
        followers = await self._follower_counter(roadmap.id)
        if followers > 0:
            noun = "follower" if followers == 1 else "followers"
            raise Conflict(
                f"Roadmap '{roadmap_id}' has {followers} {noun}; delete is only allowed with zero "
                "followers. Archive it instead to retire it while existing followers keep their "
                "progress.",
                code=ErrorCode.DELETE_HAS_FOLLOWERS,
                instance=f"/roadmaps/{roadmap_id}",
            )
        try:
            await self._repo.delete(roadmap_id)
            await self._repo.commit()
        except Exception:
            await self._repo.rollback()
            raise
        _log.info("roadmap_deleted", roadmap_id=roadmap_id, owner=user_id)

    async def _load_owned(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Load the caller's own roadmap or raise ``NotFound``.

        Owner-scoped (the repository query filters by ``owner``), so a non-owner or
        unknown ID is a 404 that never reveals another user's roadmap's existence.
        The shared load underneath every owner-scoped operation.
        """
        record = await self._repo.get_owned(roadmap_id, user_id)
        if record is None:
            raise NotFound(f"No roadmap '{roadmap_id}'.", instance=f"/roadmaps/{roadmap_id}")
        return Roadmap.model_validate(record.document)

    async def _load_readable(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Load a roadmap the caller may **read**: their own (any status) or a
        public one.

        Readability first: a private roadmap owned by someone else is a 404 that
        leaks no existence, matching the progress readability convention. This is
        the fork-source guard; unlike the progress readability check it does not
        require ``published`` status, so a caller can fork their own draft as well
        as any public roadmap. Uses the unscoped repository read (a fork source is
        not owner-scoped), then applies the readability rule here.
        """
        record = await self._repo.get(roadmap_id)
        if record is None:
            raise NotFound(f"No roadmap '{roadmap_id}'.", instance=f"/roadmaps/{roadmap_id}")
        roadmap = Roadmap.model_validate(record.document)
        if roadmap.owner != user_id and roadmap.visibility is not Visibility.PUBLIC:
            # Private roadmap owned by someone else: 404, no existence leak.
            raise NotFound(f"No roadmap '{roadmap_id}'.", instance=f"/roadmaps/{roadmap_id}")
        return roadmap

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

    async def _load_writable_draft(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Load the caller's own roadmap for a **content write** (create-content /
        patch / replace) and enforce the immutability boundary.

        A published or archived roadmap is content-immutable: any structural write
        raises ``Conflict`` with the ``IMMUTABLE`` code and a message pointing to
        fork-to-change. This is the guard that protects
        follower progress: the only way to change published content is to fork it
        into a fresh draft. Presentation edits (``edit_metadata``) do
        **not** load through here, which is why they stay allowed post-publish.
        """
        roadmap = await self._load_owned(user_id, roadmap_id)
        if roadmap.status is not RoadmapStatus.DRAFT:
            raise Conflict(
                f"Roadmap '{roadmap_id}' is {roadmap.status.value}; published content is "
                "immutable. Fork it into a new draft to make structural changes "
                "(fork-to-change).",
                code=ErrorCode.IMMUTABLE,
                instance=f"/roadmaps/{roadmap_id}",
            )
        return roadmap

    async def _load_owned_draft(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Load the caller's own roadmap for a draft-only **lifecycle** action
        (validate / publish).

        A non-owner / unknown ID is a 404 (no existence leak); a published or
        archived roadmap is a lifecycle ``Conflict`` (these actions apply only to a
        draft and change no content, so they are not the immutability/fork path).
        """
        roadmap = await self._load_owned(user_id, roadmap_id)
        if roadmap.status is not RoadmapStatus.DRAFT:
            raise Conflict(
                f"Roadmap '{roadmap_id}' is {roadmap.status.value}; only draft roadmaps can be "
                "validated or published.",
                instance=f"/roadmaps/{roadmap_id}",
            )
        return roadmap

    async def _mint_unique_roadmap_id(self, base: str) -> str:
        """Mint a globally-unique ``{slug}-{token}`` ID, silently re-rolling the
        random token on the (astronomically unlikely) collision."""
        for _ in range(MAX_ID_MINT_ATTEMPTS):
            candidate = slugs.compose_roadmap_id(base, self._token_factory())
            if not await self._repo.roadmap_id_exists(candidate):
                return candidate
        raise RuntimeError("Exhausted roadmap-ID mint attempts.")  # pragma: no cover


def _to_record(roadmap: Roadmap) -> RoadmapRecord:
    """Serialize the domain roadmap into its row: the full document plus the
    write-derived index columns."""
    return RoadmapRecord(
        id=roadmap.id,
        owner=roadmap.owner,
        title=roadmap.title,
        status=roadmap.status.value,
        visibility=roadmap.visibility.value,
        revision=roadmap.revision,
        document=roadmap.model_dump(mode="json"),
        created_at=roadmap.created_at,
        updated_at=roadmap.updated_at,
    )
