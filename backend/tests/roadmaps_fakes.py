"""In-memory test double for the roadmaps domain.

The service is tested sociably (spec section 13): the real ``slugs`` and
``assembly`` deep modules run behind ``RoadmapService``; only the repository (the
Postgres boundary) is substituted here. The fake enforces the same PK uniqueness
and owner-scoping as the ``roadmaps`` table so the create/get paths are exercised
without a database.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence

from sqlalchemy.exc import IntegrityError

from wren.roadmaps.models import RoadmapRecord
from wren.roadmaps.schemas import Roadmap


class _PkViolation(Exception):
    """Mimics an asyncpg unique/PK violation carried on IntegrityError.orig."""

    sqlstate = "23505"


class InMemoryRoadmapRepository:
    """A dict-backed :class:`RoadmapRepository` with real uniqueness + scoping."""

    def __init__(self) -> None:
        self._by_id: dict[str, RoadmapRecord] = {}
        self.commits = 0
        self.rollbacks = 0

    async def roadmap_id_exists(self, roadmap_id: str) -> bool:
        return roadmap_id in self._by_id

    async def add(self, record: RoadmapRecord) -> None:
        if record.id in self._by_id:
            raise IntegrityError("INSERT INTO roadmaps", {}, _PkViolation())
        self._by_id[record.id] = record

    async def save(self, roadmap: Roadmap) -> None:
        # Mirror the real repository: re-derive the write-managed columns from the
        # authoritative document so a transition (e.g. draft -> published) is
        # reflected on the stored record the same way Postgres would persist it.
        record = self._by_id[roadmap.id]
        record.owner = roadmap.owner
        record.title = roadmap.title
        record.status = roadmap.status.value
        record.visibility = roadmap.visibility.value
        record.revision = roadmap.revision
        record.document = roadmap.model_dump(mode="json")
        record.updated_at = roadmap.updated_at

    async def get_owned(self, roadmap_id: str, owner_id: str) -> RoadmapRecord | None:
        record = self._by_id.get(roadmap_id)
        if record is None or record.owner != owner_id:
            return None
        return record

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def sequence_token_factory(tokens: Sequence[str]) -> Callable[[], str]:
    """A deterministic token factory yielding ``tokens`` in order.

    Lets a test seed a repository with ``{slug}-{tokens[0]}`` and assert the
    service silently re-rolls to a later token (the collision re-roll rule).
    """
    it: Iterator[str] = iter(tokens)
    return lambda: next(it)
