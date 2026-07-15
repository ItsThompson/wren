"""Service-level tests for the read projections + readability.

Sociable tests through :class:`RoadmapService`'s public read methods with the
real projection modules behind it and only the repository substituted. These
concentrate on the business rules the API tests exercise only
indirectly: the study-time readability rule (owner draft preview vs a non-owner's
public published/archived read; private -> 404 no leak), the model-recoverable
404 that names sibling ids, the cursor -> 422 mapping, per-user checked scoping,
and the production checked-reader adapter in the wiring.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from progress_builders import make_record
from progress_fakes import InMemoryProgressRepository
from roadmaps_fakes import InMemoryRoadmapRepository, constant_follower_counter
from roadmaps_read_builders import (
    AUTHOR,
    CHK_ARRAYS_READ,
    ROADMAP_ID,
    SUB_ARRAYS,
    SUB_HASHING,
    build_read_roadmap,
)
from wren.core.errors import NotFound, Validation
from wren.progress.schemas import Progress
from wren.roadmaps.read_schemas import ResponseFormat, SectionInclude
from wren.roadmaps.schemas import Roadmap, RoadmapStatus, Visibility
from wren.roadmaps.service import CheckedReader, RoadmapService
from wren.roadmaps.wiring import _checked_reader

_NON_OWNER = "reader"


def _reader(*item_ids: str) -> CheckedReader:
    async def read(_user_id: str, _roadmap_id: str) -> frozenset[str]:
        return frozenset(item_ids)

    return read


def _service(roadmap: Roadmap, *, checked_reader: CheckedReader | None = None) -> RoadmapService:
    repo = InMemoryRoadmapRepository()
    repo._by_id[roadmap.id] = make_record(roadmap)
    return RoadmapService(
        repo,
        follower_counter=constant_follower_counter(),
        checked_reader=checked_reader or _reader(),
    )


# --- readability rule (owner draft preview vs non-owner published) ----------


async def test_owner_reads_their_own_draft_overview() -> None:
    service = _service(build_read_roadmap(owner=AUTHOR, status=RoadmapStatus.DRAFT))
    overview = await service.get_overview(AUTHOR, ROADMAP_ID, ResponseFormat.CONCISE)
    assert overview.roadmap_id == ROADMAP_ID
    assert overview.status is RoadmapStatus.DRAFT


async def test_non_owner_reads_a_public_published_roadmap() -> None:
    service = _service(build_read_roadmap())
    overview = await service.get_overview(_NON_OWNER, ROADMAP_ID, ResponseFormat.CONCISE)
    assert overview.roadmap_id == ROADMAP_ID


async def test_non_owner_reads_a_public_archived_roadmap() -> None:
    service = _service(build_read_roadmap(status=RoadmapStatus.ARCHIVED))
    overview = await service.get_overview(_NON_OWNER, ROADMAP_ID, ResponseFormat.CONCISE)
    assert overview.status is RoadmapStatus.ARCHIVED


async def test_non_owner_gets_not_found_on_a_private_roadmap() -> None:
    service = _service(build_read_roadmap(visibility=Visibility.PRIVATE))
    with pytest.raises(NotFound):
        await service.get_overview(_NON_OWNER, ROADMAP_ID, ResponseFormat.CONCISE)


async def test_non_owner_gets_not_found_on_a_public_draft() -> None:
    # A public draft is not discoverable: a non-owner cannot read it (no leak).
    service = _service(build_read_roadmap(status=RoadmapStatus.DRAFT, visibility=Visibility.PUBLIC))
    with pytest.raises(NotFound):
        await service.get_node(_NON_OWNER, ROADMAP_ID, SUB_ARRAYS, ResponseFormat.CONCISE)


# --- model-recoverable errors ----------------------------------------------


async def test_get_node_unknown_id_raises_not_found_naming_siblings() -> None:
    service = _service(build_read_roadmap())
    with pytest.raises(NotFound) as exc:
        await service.get_node(AUTHOR, ROADMAP_ID, "sub_ghost", ResponseFormat.CONCISE)
    # The error names the valid sibling subsection ids so an agent can self-correct.
    assert SUB_ARRAYS in exc.value.detail and SUB_HASHING in exc.value.detail


async def test_get_section_unknown_id_raises_not_found_naming_sections() -> None:
    service = _service(build_read_roadmap())
    with pytest.raises(NotFound) as exc:
        await service.get_section(AUTHOR, ROADMAP_ID, "sec_ghost", None, SectionInclude.BOTH)
    assert "sec_core" in exc.value.detail


async def test_get_section_malformed_cursor_raises_validation() -> None:
    service = _service(build_read_roadmap())
    with pytest.raises(Validation) as exc:
        await service.get_section(AUTHOR, ROADMAP_ID, "sec_core", "!!bad!!", SectionInclude.BOTH)
    assert exc.value.fields is not None and "cursor" in exc.value.fields


# --- checked scoping --------------------------------------------------------


async def test_overview_counts_come_from_the_checked_reader() -> None:
    service = _service(build_read_roadmap(), checked_reader=_reader(CHK_ARRAYS_READ))
    overview = await service.get_overview(_NON_OWNER, ROADMAP_ID, ResponseFormat.CONCISE)
    assert overview.overall.checked_items == 1


# --- production checked-reader adapter (wiring) -----------------------------


async def test_wiring_checked_reader_returns_the_checked_set() -> None:
    progress_repo = InMemoryProgressRepository()
    await progress_repo.upsert(
        Progress(
            user_id="ada",
            roadmap_id=ROADMAP_ID,
            checked={CHK_ARRAYS_READ: True, "chk_arrays-drill": False},
            updated_at=datetime(2026, 7, 15, tzinfo=UTC),
        )
    )
    reader = _checked_reader(progress_repo)  # type: ignore[arg-type]
    # Only the checked-True ids are returned...
    assert await reader("ada", ROADMAP_ID) == frozenset({CHK_ARRAYS_READ})
    # ...and a caller with no record has an empty set.
    assert await reader("grace", ROADMAP_ID) == frozenset()
