"""In-memory test double for the progress domain.

The service is tested sociably (spec section 13): the real ``summary`` / ``next``
/ ``traversal`` deep modules run behind ``ProgressService``; only the repository
(the Postgres boundary) is substituted here. The fake enforces the same
one-row-per-(user, roadmap) upsert semantics as the ``progress`` table so the
follow / update paths are exercised without a database.
"""

from __future__ import annotations

from datetime import UTC, datetime

from wren.progress.models import ProgressRecord
from wren.progress.schemas import Progress


class InMemoryProgressRepository:
    """A dict-backed :class:`ProgressRepository` keyed by (user_id, roadmap_id)."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], ProgressRecord] = {}
        self.commits = 0
        self.rollbacks = 0

    async def get(self, user_id: str, roadmap_id: str) -> ProgressRecord | None:
        return self._by_key.get((user_id, roadmap_id))

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
