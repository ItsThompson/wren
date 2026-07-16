"""ProgressService: follow, explicit-set progress, and server-computed next.

The single source of truth for progress business rules. It
receives the roadmaps read repository and its own progress repository plus the
resolved ``user_id`` (never trusted from payload), composes the pure ``summary``
and ``next`` deep modules, raises ``WrenError`` subclasses for the adapter to
render, and owns the transaction boundary (``get_session`` is yield-only).

Every method is scoped to the resolved user: progress is loaded and written only
for ``(user_id, roadmap_id)``, so another user's progress is never returned.
Starting to **follow** requires a **published** roadmap the
caller may read (owner, or public): a draft is not startable and an archived
roadmap is hidden from discovery (no new followers). Reading/updating progress is
allowed on a **published** roadmap, or on an **archived** roadmap the caller
**already follows**: an archived roadmap keeps its existing followers and their
progress, but gains no new ones (no progress row is ever created on an archived
roadmap). An unreadable roadmap is a 404 with no existence leak.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime

# Cross-domain coupling: progress reads roadmaps straight from the roadmap
# repository. Genuine coupling, not a missing re-export; a shared read-port
# abstraction is a known follow-up.
from typing import TYPE_CHECKING

from wren.core.errors import Conflict, NotFound, Validation
from wren.core.logging import get_logger
from wren.core.observability import track_failures
from wren.core.read_contract import ResponseFormat
from wren.progress.next import compute as compute_next
from wren.progress.schemas import (
    CompletionState,
    NextResult,
    Progress,
    ProgressSnapshot,
    ProgressUpdateResult,
)
from wren.progress.summary import summarize
from wren.progress.traversal import all_item_ids
from wren.roadmaps import Roadmap, RoadmapStatus, Visibility

if TYPE_CHECKING:
    from wren.progress.models import ProgressRecord
    from wren.progress.repository import ProgressRepository
    from wren.roadmaps.repository import RoadmapRepository

_log = get_logger("wren-progress")

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC)


@track_failures("progress")
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

        Idempotent: re-following returns the existing record (follow is 201).
        Following a draft or an archived roadmap is a 409 (a draft
        is not startable; an archived roadmap is retired from discovery, so it
        gains no new followers); an unreadable roadmap is a 404 (no existence
        leak). The record is private to ``user_id`` and never shown publicly.
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
        ``user_id``; another user's progress is never returned. Trackable on a
        published roadmap, or an archived one the caller already follows (an
        archived roadmap keeps its existing followers)."""
        roadmap = await self._require_trackable_readable(user_id, roadmap_id)
        progress = await self._load_or_empty(user_id, roadmap_id)
        return summarize(roadmap, progress, detailed=detailed)

    async def update(
        self, user_id: str, roadmap_id: str, item_ids: list[str], state: CompletionState
    ) -> ProgressUpdateResult:
        """Explicit-set ``item_ids`` to ``state`` (not toggle) and return the fresh
        snapshot + next suggestion.

        Idempotent on retry: setting the same items to the same state twice is a
        no-op beyond the timestamp. A foreign or nonexistent item id is a 422 and
        applies nothing (all-or-nothing validation before any write). Upserts the
        caller's private record, so the first update on a **published** roadmap
        also starts following. On an **archived** roadmap only an existing follower
        may update (the guard refuses a caller with no record, so the upsert never
        creates a new follower).
        """
        roadmap = await self._require_trackable_readable(user_id, roadmap_id)
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

    async def get_next(
        self, user_id: str, roadmap_id: str, fmt: ResponseFormat = ResponseFormat.CONCISE
    ) -> NextResult:
        """Return the next unchecked, prereq-satisfied items in path order.

        Computed server-side in:func:`progress.next.compute`,
        never delegated to the agent. Each item carries a structural ``why_now``
        and its resource links; ``detailed`` mode adds each item's
        ``path_position``. Scoped to the caller's progress. Trackable on a
        published roadmap, or an archived one the caller already follows."""
        roadmap = await self._require_trackable_readable(user_id, roadmap_id)
        progress = await self._load_or_empty(user_id, roadmap_id)
        return compute_next(roadmap, progress, fmt=fmt)

    async def set_deadline(self, user_id: str, roadmap_id: str, deadline: date | None) -> Progress:
        """Set or clear the caller's per-user deadline on the progress record.

        A ``date`` sets the deadline; ``None`` clears it. Editable and clearable at
        any time, and a past date is allowed (the countdown shows elapsed / overdue
        with no pacing signal). Upserts the caller's private
        record like :meth:`update`, so setting a deadline on a **published** roadmap
        also starts following; the same trackable guard refuses a non-follower on an
        **archived** roadmap (no phantom follower). No pacing or effort forecast is
        derived: the deadline drives a countdown only."""
        await self._require_trackable_readable(user_id, roadmap_id)
        progress = await self._load_or_empty(user_id, roadmap_id)
        updated = progress.model_copy(update={"deadline": deadline, "updated_at": self._clock()})
        await self._persist(updated)
        _log.info("deadline_set", roadmap_id=roadmap_id, user_id=user_id, cleared=deadline is None)
        return updated

    async def _load_readable(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Load a roadmap the caller may read: their own (any status) or a public
        one.

        Readability first: a private roadmap owned by someone else is a 404 that
        leaks no existence. Callers layer their own status gate on top (follow vs
        track), so this never itself grants a lifecycle transition.
        """
        record = await self._roadmaps.get(roadmap_id)
        if record is None:
            raise NotFound(f"No roadmap '{roadmap_id}'.", instance=f"/roadmaps/{roadmap_id}")
        roadmap = Roadmap.model_validate(record.document)
        if roadmap.owner != user_id and roadmap.visibility is not Visibility.PUBLIC:
            # Private roadmap owned by someone else: 404, no existence leak.
            raise NotFound(f"No roadmap '{roadmap_id}'.", instance=f"/roadmaps/{roadmap_id}")
        return roadmap

    async def _require_published_readable(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Readable **and** ``published``: the guard for **starting** to follow.

        A draft is not startable and an archived roadmap is hidden from discovery
        (it gains no new followers), so both raise ``Conflict``. Existing followers
        reach an archived roadmap's progress through
        :meth:`_require_trackable_readable` instead.
        """
        roadmap = await self._load_readable(user_id, roadmap_id)
        if roadmap.status is not RoadmapStatus.PUBLISHED:
            raise Conflict(
                f"Roadmap '{roadmap_id}' is {roadmap.status.value}; only a published roadmap can "
                "be followed.",
                instance=f"/roadmaps/{roadmap_id}",
            )
        return roadmap

    async def _require_trackable_readable(self, user_id: str, roadmap_id: str) -> Roadmap:
        """Readable **and** trackable: the guard for reading / updating progress and
        computing next.

        A published roadmap is trackable by any reader (owner, or public). An
        archived roadmap is **closed to new participation**: only a caller who
        already has a progress record (an existing follower) may read/update/track
        it, and no new progress row is ever created on it (this is what keeps
        ``count_followers`` stable for the owner's delete guard, and mirrors
        :meth:`follow`, which blocks a fresh follow on an archived roadmap). A
        ``draft`` is not trackable at all (a draft is not startable).

        Readability is checked first (:meth:`_load_readable`), so a private roadmap
        the caller does not own is a 404 with no existence leak before any status
        or followership signal is exposed.
        """
        roadmap = await self._load_readable(user_id, roadmap_id)
        if roadmap.status is RoadmapStatus.DRAFT:
            raise Conflict(
                f"Roadmap '{roadmap_id}' is a draft; only a published or archived roadmap can be "
                "tracked.",
                instance=f"/roadmaps/{roadmap_id}",
            )
        if roadmap.status is RoadmapStatus.ARCHIVED and not await self._is_follower(
            user_id, roadmap_id
        ):
            # Archived gains no new followers: a caller with no existing progress
            # record cannot start tracking it (a write here would create a phantom
            # follower via the upsert). New follows are already blocked by follow().
            raise Conflict(
                f"Roadmap '{roadmap_id}' is archived; only its existing followers can track it.",
                instance=f"/roadmaps/{roadmap_id}",
            )
        return roadmap

    async def _is_follower(self, user_id: str, roadmap_id: str) -> bool:
        """Whether the caller already has a progress record for the roadmap."""
        return await self._progress.get(user_id, roadmap_id) is not None

    def _reject_foreign_items(self, roadmap: Roadmap, roadmap_id: str, item_ids: list[str]) -> None:
        """Reject any item id not defined in this roadmap (422, applies nothing)."""
        valid = all_item_ids(roadmap)
        foreign = sorted({item_id for item_id in item_ids if item_id not in valid})
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
