"""RoadmapService: draft authoring (spec section 05).

The single source of truth for roadmap business rules. It receives a repository
and the resolved ``user_id`` (never trusted from payload), composes the pure
``slugs``/``assembly`` deep modules, raises ``WrenError`` subclasses for the
adapter to render, and owns the transaction boundary (``get_session`` is
yield-only).

This slice implements ``create_draft``, the owner-scoped ``get``, and the minimal
``validate`` / ``publish`` lifecycle (the draft -> published one-way transition
that makes content immutable). Patch, replace, fork, and the read projections are
later slices; the full structural contract composes onto ``validate`` in a later
slice (spec section 05).
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

        Loads through the shared draft-only guard (:meth:`_load_owned_draft`: 404
        for a non-owner / unknown ID, 409 immutability on a published or archived
        roadmap), then rejects a stale ``If-Match`` ``revision`` with a 409
        "re-read". :func:`patch.apply` is all-or-nothing: an invalid op raises and
        nothing is persisted; on success the ``revision`` bumps by one and only the
        changed nodes (plus any de-dup remap) are echoed.
        """
        draft = await self._load_owned_draft(user_id, roadmap_id)
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

    async def get(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Return the caller's own roadmap, or 404 (never revealing existence to
        a non-owner: the query is owner-scoped)."""
        record = await self._repo.get_owned(roadmap_id, user_id)
        if record is None:
            raise NotFound(f"No roadmap '{roadmap_id}'.", instance=f"/roadmaps/{roadmap_id}")
        return Roadmap.model_validate(record.document)

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

    async def _load_owned_draft(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Load the caller's own roadmap and assert it is a mutable draft.

        The single guard for draft-only operations: a non-owner (or unknown ID)
        gets ``NotFound`` (owner-scoped, no existence leak); a published/archived
        roadmap gets ``Conflict`` (the immutability boundary). Structural writes
        (patch / replace, later slices) load through here so a published roadmap's
        content stays immutable.
        """
        record = await self._repo.get_owned(roadmap_id, user_id)
        if record is None:
            raise NotFound(f"No roadmap '{roadmap_id}'.", instance=f"/roadmaps/{roadmap_id}")
        roadmap = Roadmap.model_validate(record.document)
        if roadmap.status is not RoadmapStatus.DRAFT:
            raise Conflict(
                f"Roadmap '{roadmap_id}' is {roadmap.status.value}; only draft roadmaps can be "
                "edited, validated, or published.",
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
