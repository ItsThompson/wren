"""Service-level tests for the dashboard + profile listing (Ticket 25).

Sociable per spec section 13: the real :class:`ListingService` runs over the
in-memory roadmap repository (the Postgres boundary substituted); the two
cross-domain lookups (handle -> owner, caller -> followed ids) are injected as the
same narrow callables the wiring binds, here backed by simple test doubles. These
assert the scoping contract (US-ACCT-03): the dashboard is caller-scoped
(authored any status + followed), and the profile exposes only published-public
roadmaps with a 404 for an unknown handle.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from roadmaps_fakes import InMemoryRoadmapRepository
from wren.core.errors import NotFound
from wren.roadmaps.listing import FollowedReader, HandleResolver, ListingService, ProfileOwner
from wren.roadmaps.models import RoadmapRecord
from wren.roadmaps.schemas import Roadmap, RoadmapStatus, Visibility

_NOW = datetime(2026, 7, 15, tzinfo=UTC)

ADA = "user_ada"
BOB = "user_bob"


def _roadmap(
    roadmap_id: str,
    owner: str,
    *,
    status: RoadmapStatus = RoadmapStatus.DRAFT,
    visibility: Visibility = Visibility.PRIVATE,
    title: str = "A Roadmap",
    subject_tags: list[str] | None = None,
    updated_at: datetime = _NOW,
) -> Roadmap:
    return Roadmap(
        id=roadmap_id,
        owner=owner,
        title=title,
        subject_tags=subject_tags or [],
        visibility=visibility,
        status=status,
        revision=1,
        created_at=_NOW,
        updated_at=updated_at,
    )


def _record(roadmap: Roadmap) -> RoadmapRecord:
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


def _handles(*owners: ProfileOwner) -> HandleResolver:
    by_handle = {owner.handle: owner for owner in owners}

    async def resolve(handle: str) -> ProfileOwner | None:
        return by_handle.get(handle)

    return resolve


def _follows(*roadmap_ids: str) -> FollowedReader:
    async def read(_user_id: str) -> list[str]:
        return list(roadmap_ids)

    return read


def _service(
    *roadmaps: Roadmap,
    handle_resolver: HandleResolver | None = None,
    followed_reader: FollowedReader | None = None,
) -> ListingService:
    repo = InMemoryRoadmapRepository()
    for roadmap in roadmaps:
        repo._by_id[roadmap.id] = _record(roadmap)
    return ListingService(
        repo,
        handle_resolver=handle_resolver or _handles(),
        followed_reader=followed_reader or _follows(),
    )


# --- dashboard --------------------------------------------------------------


async def test_dashboard_lists_authored_at_every_status() -> None:
    service = _service(
        _roadmap("r-draft", ADA, status=RoadmapStatus.DRAFT, visibility=Visibility.PRIVATE),
        _roadmap("r-pub", ADA, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC),
        _roadmap("r-arch", ADA, status=RoadmapStatus.ARCHIVED, visibility=Visibility.PUBLIC),
    )
    dashboard = await service.dashboard(ADA)
    assert {card.id for card in dashboard.authored} == {"r-draft", "r-pub", "r-arch"}
    assert dashboard.followed == []


async def test_dashboard_is_scoped_to_the_caller() -> None:
    # Another user's roadmap is never in the caller's authored list.
    service = _service(
        _roadmap("r-ada", ADA, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC),
        _roadmap("r-bob", BOB, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC),
    )
    dashboard = await service.dashboard(ADA)
    assert [card.id for card in dashboard.authored] == ["r-ada"]


async def test_dashboard_followed_loads_cross_user_roadmaps_in_follow_order() -> None:
    service = _service(
        _roadmap("r-bob", BOB, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC),
        _roadmap(
            "r-cara",
            "user_cara",
            status=RoadmapStatus.PUBLISHED,
            visibility=Visibility.PUBLIC,
        ),
        followed_reader=_follows("r-cara", "r-bob"),
    )
    dashboard = await service.dashboard(ADA)
    # Ada authored neither; both come through the followed list, order preserved.
    assert dashboard.authored == []
    assert [card.id for card in dashboard.followed] == ["r-cara", "r-bob"]


async def test_dashboard_authored_and_followed_overlap() -> None:
    # A roadmap the caller both authored and follows appears in both lists.
    service = _service(
        _roadmap("r-ada", ADA, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC),
        followed_reader=_follows("r-ada"),
    )
    dashboard = await service.dashboard(ADA)
    assert [card.id for card in dashboard.authored] == ["r-ada"]
    assert [card.id for card in dashboard.followed] == ["r-ada"]


async def test_dashboard_skips_followed_id_without_a_live_record() -> None:
    # Defensive: a followed id with no roadmap record is dropped, not crashed.
    service = _service(followed_reader=_follows("ghost-roadmap"))
    dashboard = await service.dashboard(ADA)
    assert dashboard.followed == []


async def test_dashboard_authored_ordered_newest_touched_first() -> None:
    older = datetime(2026, 7, 1, tzinfo=UTC)
    newer = datetime(2026, 7, 14, tzinfo=UTC)
    service = _service(
        _roadmap("r-old", ADA, updated_at=older),
        _roadmap("r-new", ADA, updated_at=newer),
    )
    dashboard = await service.dashboard(ADA)
    assert [card.id for card in dashboard.authored] == ["r-new", "r-old"]


async def test_dashboard_card_carries_badge_and_tag_fields() -> None:
    service = _service(
        _roadmap(
            "r-ada",
            ADA,
            status=RoadmapStatus.PUBLISHED,
            visibility=Visibility.PUBLIC,
            title="Grokking DSA",
            subject_tags=["cs", "interview-prep"],
        ),
    )
    card = (await service.dashboard(ADA)).authored[0]
    assert card.title == "Grokking DSA"
    assert card.status is RoadmapStatus.PUBLISHED
    assert card.visibility is Visibility.PUBLIC
    assert card.subject_tags == ["cs", "interview-prep"]


# --- profile ----------------------------------------------------------------


async def test_profile_returns_published_public_only() -> None:
    owner = ProfileOwner(user_id=ADA, handle="ada", display_name="ada")
    service = _service(
        _roadmap("r-draft", ADA, status=RoadmapStatus.DRAFT, visibility=Visibility.PUBLIC),
        _roadmap("r-private", ADA, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PRIVATE),
        _roadmap("r-archived", ADA, status=RoadmapStatus.ARCHIVED, visibility=Visibility.PUBLIC),
        _roadmap("r-public", ADA, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC),
        handle_resolver=_handles(owner),
    )
    profile = await service.profile("ada")
    # Only the published + public roadmap: no draft, private, or archived leak.
    assert [card.id for card in profile.roadmaps] == ["r-public"]


async def test_profile_excludes_another_users_public_roadmaps() -> None:
    owner = ProfileOwner(user_id=ADA, handle="ada", display_name="ada")
    service = _service(
        _roadmap("r-ada", ADA, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC),
        _roadmap("r-bob", BOB, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC),
        handle_resolver=_handles(owner),
    )
    profile = await service.profile("ada")
    assert [card.id for card in profile.roadmaps] == ["r-ada"]


async def test_profile_echoes_handle_and_display_name() -> None:
    owner = ProfileOwner(user_id=ADA, handle="ada", display_name="Ada Lovelace")
    service = _service(handle_resolver=_handles(owner))
    profile = await service.profile("ada")
    assert profile.handle == "ada"
    assert profile.display_name == "Ada Lovelace"
    assert profile.roadmaps == []


async def test_profile_unknown_handle_is_404() -> None:
    service = _service(handle_resolver=_handles())
    with pytest.raises(NotFound):
        await service.profile("nobody")
