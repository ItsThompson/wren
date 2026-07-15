"""Compose the roadmaps dependency graph for the external app.

Keeps the wiring (which request-scoped session backs the repository) out of the
router and the entrypoint. The production provider resolves a per-request
``AsyncSession`` via ``get_session`` and binds the SQLAlchemy repository; the
service's token factory and clock keep their process-wide defaults.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from wren.accounts.repository import SqlAlchemyAccountRepository
from wren.core.db import get_session
from wren.progress.repository import SqlAlchemyProgressRepository
from wren.roadmaps.listing import HandleResolver, ListingService, ProfileOwner
from wren.roadmaps.repository import SqlAlchemyRoadmapRepository
from wren.roadmaps.service import CheckedReader, RoadmapService


def build_roadmap_service_provider() -> Callable[[AsyncSession], RoadmapService]:
    """A FastAPI dependency that builds a request-scoped :class:`RoadmapService`."""

    def provider(session: AsyncSession = Depends(get_session)) -> RoadmapService:
        # The follower counter and the checked reader are bound to the progress
        # repository over the SAME request-scoped session (delete's zero-followers
        # guard, spec sections 05/06; and the caller's checked set for the
        # progress-aware read projections). The roadmaps service stays decoupled
        # from the progress domain: it only receives the narrow callables, not the
        # repository.
        progress_repo = SqlAlchemyProgressRepository(session)
        return RoadmapService(
            SqlAlchemyRoadmapRepository(session),
            follower_counter=progress_repo.count_followers,
            checked_reader=_checked_reader(progress_repo),
        )

    return provider


def _checked_reader(progress_repo: SqlAlchemyProgressRepository) -> CheckedReader:
    """Adapt the progress repository into the narrow :data:`CheckedReader`.

    Returns the caller's checked checklist-item ids for ``(user_id, roadmap_id)``
    (an empty set when they have no progress record), so a read projection can
    compute per-section counts and per-item done-state without the roadmaps domain
    importing the progress repository's type into its own logic."""

    async def read(user_id: str, roadmap_id: str) -> frozenset[str]:
        record = await progress_repo.get(user_id, roadmap_id)
        if record is None:
            return frozenset()
        return frozenset(item_id for item_id, is_checked in record.checked.items() if is_checked)

    return read


def build_listing_service_provider() -> Callable[[AsyncSession], ListingService]:
    """A FastAPI dependency that builds a request-scoped :class:`ListingService`.

    Composes the dashboard + profile reads across three domains over ONE
    request-scoped session: the roadmaps repository (owned + published-public
    listings), the accounts repository (handle -> owner resolution, adapted to the
    narrow :data:`HandleResolver`), and the progress repository (the caller's
    followed ids, adapted to the narrow :data:`FollowedReader`). The listing
    service receives only the narrow callables, so the roadmaps domain stays
    decoupled from accounts and progress (the wiring is the only composition
    point).
    """

    def provider(session: AsyncSession = Depends(get_session)) -> ListingService:
        account_repo = SqlAlchemyAccountRepository(session)
        progress_repo = SqlAlchemyProgressRepository(session)
        return ListingService(
            SqlAlchemyRoadmapRepository(session),
            handle_resolver=_handle_resolver(account_repo),
            followed_reader=progress_repo.list_followed_roadmap_ids,
        )

    return provider


def _handle_resolver(account_repo: SqlAlchemyAccountRepository) -> HandleResolver:
    """Adapt the accounts repository into the narrow :data:`HandleResolver`.

    Resolves a public handle to its :class:`ProfileOwner` (the ``users.id`` used to
    scope the profile query plus the handle/display name echoed back), or ``None``
    when no such user exists (-> 404). The display name mirrors the accounts
    ``PublicProfile`` stub (the username is the public handle) without importing
    the accounts service, keeping the dependency arrow one-way."""

    async def resolve(handle: str) -> ProfileOwner | None:
        user = await account_repo.get_by_username(handle)
        if user is None:
            return None
        return ProfileOwner(user_id=user.id, handle=user.username, display_name=user.username)

    return resolve
