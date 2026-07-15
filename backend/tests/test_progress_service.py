"""Sociable unit tests for:class:`ProgressService`.

The real ``summary`` / ``next`` / ``traversal`` deep modules run behind the
service; only the two repositories (the Postgres boundary) are substituted with
in-memory fakes. Covers the follow guard (published-only, idempotent), the
explicit-set update (idempotent, foreign-id 422 applies nothing), the derived
snapshot, the server-computed next, and per-user scoping.
"""

from __future__ import annotations

from datetime import date

import pytest

from progress_builders import (
    CHK_ARRAYS_DRILL,
    CHK_ARRAYS_READ,
    CHK_HASH,
    build_roadmap,
    make_record,
)
from progress_fakes import InMemoryProgressRepository
from roadmaps_fakes import InMemoryRoadmapRepository
from wren.core.errors import Conflict, NotFound, Validation
from wren.progress.schemas import CompletionState
from wren.progress.service import ProgressService
from wren.roadmaps.read_schemas import ResponseFormat
from wren.roadmaps.schemas import Roadmap, RoadmapStatus, Visibility

_OWNER = "owner"
_FOLLOWER = "follower"


def _service(
    *roadmaps: Roadmap,
) -> tuple[ProgressService, InMemoryRoadmapRepository, InMemoryProgressRepository]:
    roadmap_repo = InMemoryRoadmapRepository()
    for roadmap in roadmaps:
        roadmap_repo._by_id[roadmap.id] = make_record(roadmap)
    progress_repo = InMemoryProgressRepository()
    return ProgressService(roadmap_repo, progress_repo), roadmap_repo, progress_repo


# --- follow -----------------------------------------------------------------


async def test_follow_a_published_roadmap_creates_a_private_record() -> None:
    roadmap = build_roadmap()
    service, _, progress_repo = _service(roadmap)

    progress = await service.follow(_FOLLOWER, roadmap.id)

    assert progress.user_id == _FOLLOWER
    assert progress.roadmap_id == roadmap.id
    assert progress.checked == {}
    assert await progress_repo.get(_FOLLOWER, roadmap.id) is not None
    assert progress_repo.commits == 1


async def test_follow_is_idempotent() -> None:
    roadmap = build_roadmap()
    service, _, progress_repo = _service(roadmap)

    await service.follow(_FOLLOWER, roadmap.id)
    # A second follow after some progress returns the existing record, not a reset.
    await service.update(_FOLLOWER, roadmap.id, [CHK_ARRAYS_READ], CompletionState.COMPLETE)
    again = await service.follow(_FOLLOWER, roadmap.id)

    assert again.checked == {CHK_ARRAYS_READ: True}


async def test_follow_a_draft_is_a_409() -> None:
    draft = build_roadmap(status=RoadmapStatus.DRAFT, visibility=Visibility.PUBLIC)
    service, _, _ = _service(draft)

    with pytest.raises(Conflict):
        await service.follow(_FOLLOWER, draft.id)


async def test_follow_an_unknown_roadmap_is_a_404() -> None:
    service, _, _ = _service()
    with pytest.raises(NotFound):
        await service.follow(_FOLLOWER, "never-minted-0000")


async def test_follow_a_private_roadmap_owned_by_another_is_a_404_no_leak() -> None:
    private = build_roadmap(owner=_OWNER, visibility=Visibility.PRIVATE)
    service, _, _ = _service(private)

    with pytest.raises(NotFound):
        await service.follow(_FOLLOWER, private.id)


async def test_owner_can_follow_their_own_private_published_roadmap() -> None:
    private = build_roadmap(owner=_OWNER, visibility=Visibility.PRIVATE)
    service, _, _ = _service(private)

    progress = await service.follow(_OWNER, private.id)
    assert progress.user_id == _OWNER


# --- update (explicit set) --------------------------------------------------


async def test_update_sets_items_complete_and_returns_snapshot_and_next() -> None:
    roadmap = build_roadmap()
    service, _, _ = _service(roadmap)

    result = await service.update(
        _FOLLOWER, roadmap.id, [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL], CompletionState.COMPLETE
    )

    assert result.progress.checked_items == 2
    assert result.progress.checked_ids == sorted([CHK_ARRAYS_READ, CHK_ARRAYS_DRILL])
    # Next advances past the now-complete arrays subsection.
    assert [item.item_id for item in result.next.items] == [CHK_HASH]


async def test_update_is_idempotent_on_retry() -> None:
    roadmap = build_roadmap()
    service, _, _ = _service(roadmap)

    first = await service.update(_FOLLOWER, roadmap.id, [CHK_ARRAYS_READ], CompletionState.COMPLETE)
    second = await service.update(
        _FOLLOWER, roadmap.id, [CHK_ARRAYS_READ], CompletionState.COMPLETE
    )

    assert first.progress.checked_ids == second.progress.checked_ids == [CHK_ARRAYS_READ]


async def test_update_incomplete_is_an_explicit_set_not_a_toggle() -> None:
    roadmap = build_roadmap()
    service, _, _ = _service(roadmap)

    await service.update(_FOLLOWER, roadmap.id, [CHK_ARRAYS_READ], CompletionState.COMPLETE)
    # Setting incomplete twice stays incomplete (not toggled back on).
    await service.update(_FOLLOWER, roadmap.id, [CHK_ARRAYS_READ], CompletionState.INCOMPLETE)
    result = await service.update(
        _FOLLOWER, roadmap.id, [CHK_ARRAYS_READ], CompletionState.INCOMPLETE
    )

    assert result.progress.checked_items == 0


async def test_update_with_a_foreign_item_id_is_a_422_and_applies_nothing() -> None:
    roadmap = build_roadmap()
    service, _, progress_repo = _service(roadmap)

    with pytest.raises(Validation) as exc:
        await service.update(
            _FOLLOWER, roadmap.id, [CHK_ARRAYS_READ, "chk_ghost"], CompletionState.COMPLETE
        )
    assert exc.value.fields is not None and "item_ids" in exc.value.fields
    # Nothing was persisted: the whole batch was rejected before any write.
    assert await progress_repo.get(_FOLLOWER, roadmap.id) is None
    assert progress_repo.commits == 0


async def test_update_on_a_draft_is_a_409() -> None:
    draft = build_roadmap(status=RoadmapStatus.DRAFT)
    service, _, _ = _service(draft)

    with pytest.raises(Conflict):
        await service.update(_FOLLOWER, draft.id, [CHK_ARRAYS_READ], CompletionState.COMPLETE)


# --- get + get_next ---------------------------------------------------------


async def test_get_returns_an_empty_snapshot_before_following() -> None:
    roadmap = build_roadmap()
    service, _, _ = _service(roadmap)

    snapshot = await service.get(_FOLLOWER, roadmap.id, detailed=True)
    assert snapshot.checked_items == 0
    assert snapshot.total_items == 4
    assert snapshot.checked_ids == []


async def test_get_next_before_following_returns_the_first_items() -> None:
    roadmap = build_roadmap()
    service, _, _ = _service(roadmap)

    result = await service.get_next(_FOLLOWER, roadmap.id)
    assert [item.item_id for item in result.items] == [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL]


async def test_get_next_detailed_adds_path_position_concise_omits_it() -> None:
    roadmap = build_roadmap()
    service, _, _ = _service(roadmap)

    concise = await service.get_next(_FOLLOWER, roadmap.id, ResponseFormat.CONCISE)
    assert all(item.path_position is None for item in concise.items)

    detailed = await service.get_next(_FOLLOWER, roadmap.id, ResponseFormat.DETAILED)
    # Arrays is first in suggested_path -> position 1; why_now stays structural.
    assert all(item.path_position == 1 for item in detailed.items)
    assert detailed.items[0].why_now.startswith("Next unchecked subsection in the suggested path")
    assert detailed.remaining_in_path == 3


# --- deadline (set / clear, per-user, countdown only) -----------------------


async def test_set_deadline_sets_the_per_user_deadline() -> None:
    roadmap = build_roadmap()
    service, _, _ = _service(roadmap)

    progress = await service.set_deadline(_FOLLOWER, roadmap.id, date(2026, 12, 1))
    assert progress.deadline == date(2026, 12, 1)
    # The snapshot echoes the deadline so the countdown can render.
    snapshot = await service.get(_FOLLOWER, roadmap.id, detailed=False)
    assert snapshot.deadline == date(2026, 12, 1)


async def test_set_deadline_is_editable_and_clearable_at_any_time() -> None:
    roadmap = build_roadmap()
    service, _, _ = _service(roadmap)

    await service.set_deadline(_FOLLOWER, roadmap.id, date(2026, 12, 1))
    # Editable: a second set replaces the date.
    await service.set_deadline(_FOLLOWER, roadmap.id, date(2027, 1, 15))
    # Clearable: passing None removes it.
    cleared = await service.set_deadline(_FOLLOWER, roadmap.id, None)
    assert cleared.deadline is None
    assert (await service.get(_FOLLOWER, roadmap.id, detailed=False)).deadline is None


async def test_set_deadline_in_the_past_is_allowed() -> None:
    # A past deadline is elapsed/overdue (no pacing signal), never rejected.
    roadmap = build_roadmap()
    service, _, _ = _service(roadmap)

    progress = await service.set_deadline(_FOLLOWER, roadmap.id, date(2000, 1, 1))
    assert progress.deadline == date(2000, 1, 1)


async def test_set_deadline_preserves_existing_checked_items() -> None:
    # Setting a deadline must not disturb progress: it only touches the date.
    roadmap = build_roadmap()
    service, _, _ = _service(roadmap)

    await service.update(_FOLLOWER, roadmap.id, [CHK_ARRAYS_READ], CompletionState.COMPLETE)
    await service.set_deadline(_FOLLOWER, roadmap.id, date(2026, 12, 1))
    snapshot = await service.get(_FOLLOWER, roadmap.id, detailed=True)
    assert snapshot.checked_ids == [CHK_ARRAYS_READ]
    assert snapshot.deadline == date(2026, 12, 1)


async def test_set_deadline_on_a_published_roadmap_starts_following() -> None:
    # Mirrors update's upsert: setting a deadline on a published roadmap the
    # caller has not explicitly followed creates their private record.
    roadmap = build_roadmap()
    service, _, progress_repo = _service(roadmap)

    await service.set_deadline(_FOLLOWER, roadmap.id, date(2026, 12, 1))
    assert await progress_repo.get(_FOLLOWER, roadmap.id) is not None


async def test_set_deadline_on_a_draft_is_a_409() -> None:
    draft = build_roadmap(status=RoadmapStatus.DRAFT)
    service, _, _ = _service(draft)

    with pytest.raises(Conflict):
        await service.set_deadline(_FOLLOWER, draft.id, date(2026, 12, 1))


async def test_set_deadline_is_scoped_per_user() -> None:
    roadmap = build_roadmap()
    service, _, _ = _service(roadmap)

    await service.set_deadline(_FOLLOWER, roadmap.id, date(2026, 12, 1))
    # Another user has no deadline of their own.
    other = await service.get("someone-else", roadmap.id, detailed=False)
    assert other.deadline is None


async def test_set_deadline_on_a_public_archived_roadmap_by_a_non_follower_is_a_409() -> None:
    # Archived gains no new followers: a non-follower's set_deadline is refused
    # before any write, so no phantom progress row is created.
    archived = build_roadmap(status=RoadmapStatus.ARCHIVED, visibility=Visibility.PUBLIC)
    service, _, progress_repo = _service(archived)

    with pytest.raises(Conflict):
        await service.set_deadline(_FOLLOWER, archived.id, date(2026, 12, 1))
    assert await progress_repo.get(_FOLLOWER, archived.id) is None
    assert progress_repo.commits == 0


# --- per-user scoping -------------------------------------------------------


async def test_progress_is_scoped_per_user() -> None:
    roadmap = build_roadmap()
    service, _, _ = _service(roadmap)

    await service.update(
        _FOLLOWER, roadmap.id, [CHK_ARRAYS_READ, CHK_ARRAYS_DRILL], CompletionState.COMPLETE
    )
    # A different user sees their own (empty) progress, never the follower's.
    other = await service.get("someone-else", roadmap.id, detailed=True)
    assert other.checked_items == 0
    assert other.checked_ids == []


# --- transaction boundary ---------------------------------------------------


class _FailingProgressRepository(InMemoryProgressRepository):
    """Upsert always fails, to exercise the service's rollback path."""

    async def upsert(self, progress: object) -> None:  # type: ignore[override]
        raise RuntimeError("boom")


async def test_a_persist_failure_rolls_back_and_propagates() -> None:
    roadmap = build_roadmap()
    roadmap_repo = InMemoryRoadmapRepository()
    roadmap_repo._by_id[roadmap.id] = make_record(roadmap)
    progress_repo = _FailingProgressRepository()
    service = ProgressService(roadmap_repo, progress_repo)

    with pytest.raises(RuntimeError):
        await service.follow(_FOLLOWER, roadmap.id)
    assert progress_repo.rollbacks == 1
    assert progress_repo.commits == 0


# --- archived roadmaps keep existing followers ------------------------------


async def test_get_on_an_archived_roadmap_is_allowed_for_a_follower() -> None:
    # Archiving hides a roadmap from discovery but must NOT break its existing
    # followers: a follower keeps reading their progress after it is archived.
    roadmap = build_roadmap(visibility=Visibility.PUBLIC)
    service, roadmap_repo, _ = _service(roadmap)
    await service.update(_FOLLOWER, roadmap.id, [CHK_ARRAYS_READ], CompletionState.COMPLETE)

    # The owner archives it (simulate the persisted archived state on the record).
    await roadmap_repo.save(roadmap.model_copy(update={"status": RoadmapStatus.ARCHIVED}))

    snapshot = await service.get(_FOLLOWER, roadmap.id, detailed=True)
    assert snapshot.checked_items == 1
    assert snapshot.checked_ids == [CHK_ARRAYS_READ]


async def test_update_and_next_on_an_archived_roadmap_keep_working_for_a_follower() -> None:
    roadmap = build_roadmap(visibility=Visibility.PUBLIC)
    service, roadmap_repo, _ = _service(roadmap)
    await service.follow(_FOLLOWER, roadmap.id)
    await roadmap_repo.save(roadmap.model_copy(update={"status": RoadmapStatus.ARCHIVED}))

    # An existing follower can still record progress and compute their next items.
    result = await service.update(
        _FOLLOWER, roadmap.id, [CHK_ARRAYS_READ], CompletionState.COMPLETE
    )
    assert result.progress.checked_ids == [CHK_ARRAYS_READ]
    nxt = await service.get_next(_FOLLOWER, roadmap.id)
    assert nxt.complete is False
    assert CHK_ARRAYS_READ not in [item.item_id for item in nxt.items]


async def test_follow_on_an_archived_roadmap_is_a_409_no_new_followers() -> None:
    # Archived = retired from discovery, so it gains NO new followers: a fresh
    # follow is a 409 (existing followers keep access via get/update/get_next).
    archived = build_roadmap(status=RoadmapStatus.ARCHIVED, visibility=Visibility.PUBLIC)
    service, _, _ = _service(archived)
    with pytest.raises(Conflict):
        await service.follow(_FOLLOWER, archived.id)


async def test_read_of_an_archived_private_roadmap_by_a_non_follower_is_a_404_no_leak() -> None:
    # A non-owner, non-follower cannot read an archived PRIVATE roadmap: 404 with
    # no existence leak (readability is checked before the trackable status gate).
    archived = build_roadmap(
        owner=_OWNER, status=RoadmapStatus.ARCHIVED, visibility=Visibility.PRIVATE
    )
    service, _, _ = _service(archived)
    with pytest.raises(NotFound):
        await service.get(_FOLLOWER, archived.id, detailed=True)
    with pytest.raises(NotFound):
        await service.get_next(_FOLLOWER, archived.id)


async def test_update_on_a_public_archived_roadmap_by_a_non_follower_creates_no_follower() -> None:
    # The phantom-follower guard: a non-follower's update on a PUBLIC archived
    # roadmap is refused before any write, so the upsert cannot mint a new
    # progress row (which would be a new follower and could block the owner's
    # delete). Archived gains no new followers, via update just as via follow.
    archived = build_roadmap(status=RoadmapStatus.ARCHIVED, visibility=Visibility.PUBLIC)
    service, _, progress_repo = _service(archived)
    with pytest.raises(Conflict):
        await service.update(_FOLLOWER, archived.id, [CHK_ARRAYS_READ], CompletionState.COMPLETE)
    # No phantom follower: no row was created and the follower count stays zero.
    assert await progress_repo.get(_FOLLOWER, archived.id) is None
    assert await progress_repo.count_followers(archived.id) == 0
    assert progress_repo.commits == 0


async def test_get_next_on_a_public_archived_roadmap_by_a_non_follower_is_a_409() -> None:
    # A non-follower cannot start tracking an archived roadmap, so get_next is
    # refused too (archived is closed to new participation).
    archived = build_roadmap(status=RoadmapStatus.ARCHIVED, visibility=Visibility.PUBLIC)
    service, _, _ = _service(archived)
    with pytest.raises(Conflict):
        await service.get_next(_FOLLOWER, archived.id)


async def test_get_on_a_public_archived_roadmap_by_a_non_follower_is_a_409() -> None:
    # Consistent with update/get_next: a non-follower cannot track an archived
    # roadmap. (A private archived roadmap is a 404 first; this one is public.)
    archived = build_roadmap(status=RoadmapStatus.ARCHIVED, visibility=Visibility.PUBLIC)
    service, _, _ = _service(archived)
    with pytest.raises(Conflict):
        await service.get(_FOLLOWER, archived.id, detailed=True)
