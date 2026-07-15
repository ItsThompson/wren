"""RoadmapService: draft authoring (spec section 05).

The single source of truth for roadmap business rules. It receives a repository
and the resolved ``user_id`` (never trusted from payload), composes the pure
``slugs``/``assembly`` deep modules, raises ``WrenError`` subclasses for the
adapter to render, and owns the transaction boundary (``get_session`` is
yield-only).

This slice implements ``create_draft``, the owner-scoped ``get``, the iterative
``patch_draft``, the full-document ``replace_draft`` import escape hatch, and the
minimal ``validate`` / ``publish`` lifecycle (the draft -> published one-way
transition that makes content immutable). Fork and the read projections are later
slices; the full structural contract composes onto ``validate`` in a later slice
(spec section 05).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from wren.core.errors import Conflict, ErrorCode, NotFound, Validation, Violation
from wren.core.logging import get_logger
from wren.roadmaps import patch, slugs
from wren.roadmaps.assembly import assemble_draft
from wren.roadmaps.config import MAX_ID_MINT_ATTEMPTS
from wren.roadmaps.models import RoadmapRecord
from wren.roadmaps.repository import RoadmapRepository
from wren.roadmaps.schemas import (
    PatchOp,
    PatchResult,
    Roadmap,
    RoadmapCreated,
    RoadmapInput,
    RoadmapReplaced,
    RoadmapStatus,
)
from wren.roadmaps.validation import validate_structure

_log = get_logger("wren-roadmaps")

TokenFactory = Callable[[], str]
Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RoadmapService:
    """Business rules for authoring roadmap drafts."""

    def __init__(
        self,
        repo: RoadmapRepository,
        *,
        token_factory: TokenFactory = slugs.random_token,
        clock: Clock = _utcnow,
    ) -> None:
        self._repo = repo
        # The random-token source and clock are injected so tests can force an
        # ID collision (re-roll) and pin timestamps without patching globals.
        self._token_factory = token_factory
        self._clock = clock

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
        concurrency (spec sections 05/07).

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
        """Replace the caller's entire draft from a full ``RoadmapInput`` (spec
        sections 04/06/07).

        The documented **import escape hatch**, never the iterative path: it rebuilds
        the whole document rather than editing in place. Loads through the same
        content-write guard as :meth:`patch_draft` (:meth:`_load_writable_draft`: 404
        for a non-owner / unknown ID, 409 ``IMMUTABLE`` on a published/archived
        roadmap) and is guarded by the same optimistic-concurrency ``If-Match``
        ``revision`` (stale -> 409 "re-read"), because a full replace is a
        structure-mutating write (spec section 06).

        ID semantics (spec section 04 v1.1): the roadmap's own ID (the route param)
        is unchanged, nodes carrying a ``proposed_id`` keep it, and every other node
        is re-minted, all via the shared :func:`assemble_draft` mint-then-resolve
        pass. ``created_at`` and ``owner`` are preserved; ``revision`` bumps by one
        and the ``proposed_id -> minted_id`` remap is returned so the author can
        reconcile any de-duped reference.
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
            update={"revision": draft.revision + 1, "created_at": draft.created_at}
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
        """Return the caller's own roadmap, or 404 (never revealing existence to
        a non-owner: the query is owner-scoped). Any status, since a read is not a
        draft-only operation."""
        return await self._load_owned(user_id, roadmap_id)

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

    async def _load_writable_draft(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Load the caller's own roadmap for a **content write** (create-content /
        patch / replace) and enforce the immutability boundary.

        A published or archived roadmap is content-immutable: any structural write
        raises ``Conflict`` with the ``IMMUTABLE`` code and a message pointing to
        fork-to-change (spec sections 04/05/07). This is the guard that protects
        follower progress: the only way to change published content is to fork it
        into a fresh draft. Presentation edits (``edit_metadata``, Ticket 14) do
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
