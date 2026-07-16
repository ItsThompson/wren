"""In-memory test double for the progress domain.

The service is tested sociably: the real ``summary`` / ``next``
/ ``traversal`` deep modules run behind ``ProgressService``; only the repository
(the Postgres boundary) is substituted here. The fake enforces the same
one-row-per-(user, roadmap) upsert semantics as the ``progress`` table so the
follow / update paths are exercised without a database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from wren.progress.models import ProgressRecord

if TYPE_CHECKING:
    from wren.progress.schemas import Progress


class InMemoryProgressRepository:
    """A dict-backed :class:`ProgressRepository` keyed by (user_id, roadmap_id)."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], ProgressRecord] = {}
        self.commits = 0
        self.rollbacks = 0

    async def get(self, user_id: str, roadmap_id: str) -> ProgressRecord | None:
        return self._by_key.get((user_id, roadmap_id))

    async def list_followed_roadmap_ids(self, user_id: str) -> list[str]:
        # Mirror the real query: the caller's followed roadmap ids, newest-updated
        # first (updated_at desc, roadmap_id asc tiebreak). Stable sort by id then
        # by updated_at descending keeps id as the ascending tiebreak.
        rows = [record for (uid, _rid), record in self._by_key.items() if uid == user_id]
        by_id = sorted(rows, key=lambda record: record.roadmap_id)
        ordered = sorted(by_id, key=lambda record: record.updated_at, reverse=True)
        return [record.roadmap_id for record in ordered]

    async def count_followers(self, roadmap_id: str) -> int:
        # Mirror the real indexed count: how many progress rows reference this
        # roadmap, across all users (the roadmaps delete guard reads this).
        return sum(1 for (_user, rid) in self._by_key if rid == roadmap_id)

    async def upsert(self, progress: Progress) -> None:
        key = (progress.user_id, progress.roadmap_id)
        existing = self._by_key.get(key)
        if existing is None:
            self._by_key[key] = ProgressRecord(
                user_id=progress.user_id,
                roadmap_id=progress.roadmap_id,
                deadline=progress.deadline,
                checked=dict(progress.checked),
                created_at=datetime.now(UTC),
                updated_at=progress.updated_at,
            )
            return
        # Conflict path: refresh the mutable columns, keep created_at (mirrors the
        # real on_conflict_do_update).
        existing.deadline = progress.deadline
        existing.checked = dict(progress.checked)
        existing.updated_at = progress.updated_at

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
