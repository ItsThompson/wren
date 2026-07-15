"""ProgressService: follow, explicit-set progress, and server-computed next.

The single source of truth for progress business rules (spec section 05). It
receives the roadmaps read repository and its own progress repository plus the
resolved ``user_id`` (never trusted from payload), composes the pure ``summary``
and ``next`` deep modules, raises ``WrenError`` subclasses for the adapter to
render, and owns the transaction boundary (``get_session`` is yield-only).

Every method is scoped to the resolved user: progress is loaded and written only
for ``(user_id, roadmap_id)``, so another user's progress is never returned
(spec sections 05/08). Progress operations require a **published** roadmap that
the caller may read (owner, or public): an unreadable roadmap is a 404 with no
existence leak, and a non-published one is a 409 (a draft is not startable).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from wren.core.errors import Conflict, NotFound, Validation
from wren.core.logging import get_logger
from wren.progress.models import ProgressRecord
from wren.progress.next import compute as compute_next
from wren.progress.repository import ProgressRepository
from wren.progress.schemas import (
    CompletionState,
    NextResult,
    Progress,
    ProgressSnapshot,
    ProgressUpdateResult,
)
from wren.progress.summary import summarize
from wren.progress.traversal import all_item_ids
from wren.roadmaps.repository import RoadmapRepository
from wren.roadmaps.schemas import Roadmap, RoadmapStatus, Visibility

_log = get_logger("wren-progress")

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ProgressService:
    """Business rules for following roadmaps and tracking progress."""

    def __init__(
        self,
        roadmap_repo: RoadmapRepository,
        progress_repo: ProgressRepository,
        *,
        clock: Clock = _utcnow,
    ) -> None:
        self._roadmaps = roadmap_repo
        self._progress = progress_repo
        # Injected so tests can pin timestamps without patching globals.
        self._clock = clock

    async def follow(self, user_id: str, roadmap_id: str) -> Progress:
        """Start following a published roadmap: create the private progress record.

        Idempotent: re-following returns the existing record (spec section 06
        follow is 201). Following a draft is a 409 (a draft is not startable);
        an unreadable roadmap is a 404 (no existence leak). The record is private
        to ``user_id`` and never shown publicly.
        """
        await self._require_published_readable(user_id, roadmap_id)
        existing = await self._progress.get(user_id, roadmap_id)
        if existing is not None:
            return _record_to_progress(existing)
        progress = Progress(user_id=user_id, roadmap_id=roadmap_id, updated_at=self._clock())
        await self._persist(progress)
        _log.info("roadmap_followed", roadmap_id=roadmap_id, user_id=user_id)
        return progress

    async def get(self, user_id: str, roadmap_id: str, detailed: bool) -> ProgressSnapshot:
        """Return the caller's progress snapshot against the roadmap.

        Recomputed from the roadmap + the caller's record (an empty record when
        they have not started), so the counts never drift. Scoped to
        ``user_id``; another user's progress is never returned."""
        roadmap = await self._require_published_readable(user_id, roadmap_id)
        progress = await self._load_or_empty(user_id, roadmap_id)
        return summarize(roadmap, progress, detailed=detailed)

    async def update(
        self, user_id: str, roadmap_id: str, item_ids: list[str], state: CompletionState
    ) -> ProgressUpdateResult:
        """Explicit-set ``item_ids`` to ``state`` (not toggle) and return the fresh
        snapshot + next suggestion (spec section 07).

        Idempotent on retry: setting the same items to the same state twice is a
        no-op beyond the timestamp. A foreign or nonexistent item id is a 422 and
        applies nothing (all-or-nothing validation before any write). Upserts the
        caller's private record, so the first update also starts following.
        """
        roadmap = await self._require_published_readable(user_id, roadmap_id)
        self._reject_foreign_items(roadmap, roadmap_id, item_ids)
        progress = await self._load_or_empty(user_id, roadmap_id)
        checked = dict(progress.checked)
        for item_id in item_ids:
            if state is CompletionState.COMPLETE:
                checked[item_id] = True
            else:
                # Explicit-set to incomplete drops the key so the map holds only
                # checked items (keeps it lean; the set is idempotent).
                checked.pop(item_id, None)
        updated = progress.model_copy(update={"checked": checked, "updated_at": self._clock()})
        await self._persist(updated)
        _log.info(
            "progress_updated",
            roadmap_id=roadmap_id,
            user_id=user_id,
            items=len(item_ids),
            state=state.value,
        )
        return ProgressUpdateResult(
            progress=summarize(roadmap, updated, detailed=True),
            next=compute_next(roadmap, updated),
        )

    async def get_next(self, user_id: str, roadmap_id: str) -> NextResult:
        """Return the next unchecked, prereq-satisfied items in path order.

        Computed server-side in :func:`progress.next.compute` (spec section 07),
        never delegated to the agent. Scoped to the caller's progress."""
        roadmap = await self._require_published_readable(user_id, roadmap_id)
        progress = await self._load_or_empty(user_id, roadmap_id)
        return compute_next(roadmap, progress)

    async def _require_published_readable(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Load a roadmap the caller may track: readable and published.

        Readability first (owner, or public), so a private roadmap the caller
        does not own is a 404 that leaks no existence. Then the published gate: a
        draft/archived roadmap is a 409 (a draft is not startable). This is the
        shared guard for follow / get / update / get_next.
        """
        record = await self._roadmaps.get(roadmap_id)
        if record is None:
            raise NotFound(f"No roadmap '{roadmap_id}'.", instance=f"/roadmaps/{roadmap_id}")
        roadmap = Roadmap.model_validate(record.document)
        if roadmap.owner != user_id and roadmap.visibility is not Visibility.PUBLIC:
            # Private roadmap owned by someone else: 404, no existence leak.
            raise NotFound(f"No roadmap '{roadmap_id}'.", instance=f"/roadmaps/{roadmap_id}")
        if roadmap.status is not RoadmapStatus.PUBLISHED:
            raise Conflict(
                f"Roadmap '{roadmap_id}' is {roadmap.status.value}; only a published roadmap can "
                "be followed or tracked.",
                instance=f"/roadmaps/{roadmap_id}",
            )
        return roadmap

    def _reject_foreign_items(self, roadmap: Roadmap, roadmap_id: str, item_ids: list[str]) -> None:
        """Reject any item id not defined in this roadmap (422, applies nothing)."""
        foreign = sorted({item_id for item_id in item_ids if item_id not in all_item_ids(roadmap)})
        if foreign:
            plural = "id" if len(foreign) == 1 else "ids"
            raise Validation(
                f"{len(foreign)} item {plural} do not belong to roadmap '{roadmap_id}'.",
                fields={"item_ids": "unknown item id(s): " + ", ".join(foreign)},
                instance=f"/roadmaps/{roadmap_id}",
            )

    async def _load_or_empty(self, user_id: str, roadmap_id: str) -> Progress:
        """The caller's progress record, or an empty one when they have not started."""
        record = await self._progress.get(user_id, roadmap_id)
        if record is None:
            return Progress(user_id=user_id, roadmap_id=roadmap_id, updated_at=self._clock())
        return _record_to_progress(record)

    async def _persist(self, progress: Progress) -> None:
        """Upsert the caller's record inside the service-owned transaction."""
        try:
            await self._progress.upsert(progress)
            await self._progress.commit()
        except Exception:
            await self._progress.rollback()
            raise


def _record_to_progress(record: ProgressRecord) -> Progress:
    """Rebuild the domain :class:`Progress` from its persisted row."""
    return Progress(
        user_id=record.user_id,
        roadmap_id=record.roadmap_id,
        deadline=record.deadline,
        checked=dict(record.checked),
        updated_at=record.updated_at,
    )
