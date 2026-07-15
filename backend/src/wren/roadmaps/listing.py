"""ListingService: the private dashboard and the public profile.

The read-only listing surface behind ``GET /me/dashboard`` and
``GET /users/{handle}``. It is a separate service
from :class:`~wren.roadmaps.service.RoadmapService` (authoring/lifecycle) because
it is a distinct read concern and needs cross-domain lookups the authoring service
does not: a **handle resolver** (accounts) and a **followed-roadmaps reader**
(progress). Both are injected as narrow callables (never the foreign repository),
so the roadmaps domain stays decoupled from accounts and progress exactly as
:class:`RoadmapService` does with its follower counter and checked reader; the
wiring composes them.

Scoping:

- **Dashboard** is private and caller-scoped: everything the caller **authored**
  (any status) plus everything they **follow**. Another user's dashboard is never
  returned (the ``user_id`` is the resolved session identity).
- **Profile** is public and viewer-agnostic: only the handle owner's **published,
  public** roadmaps. Drafts, private, and archived roadmaps never appear, and
  following is never exposed (no social graph). An unknown handle is a 404.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from wren.core.errors import NotFound
from wren.core.observability import track_failures
from wren.roadmaps.list_schemas import Dashboard, Profile, RoadmapCard
from wren.roadmaps.models import RoadmapRecord
from wren.roadmaps.repository import RoadmapRepository
from wren.roadmaps.schemas import Roadmap


@dataclass(frozen=True)
class ProfileOwner:
    """The public identity behind a handle, resolved from the accounts domain.

    ``user_id`` is the ``roadmaps.owner`` key used to scope the profile query;
    ``handle`` and ``display_name`` are echoed in the response."""

    user_id: str
    handle: str
    display_name: str


# How the profile learns the public identity behind a handle. A narrow injected
# callable (not the accounts repository) resolving a handle to its owner, or
# ``None`` when no such user exists (-> 404). The wiring binds it to the accounts
# repository; tests substitute a dict lookup.
HandleResolver = Callable[[str], Awaitable[ProfileOwner | None]]
# How the dashboard learns which roadmaps the caller follows. A narrow injected
# callable (not the progress repository) returning the followed roadmap ids in
# display order. The wiring binds it to the progress repository; tests substitute
# a closure over a seeded set.
FollowedReader = Callable[[str], Awaitable[list[str]]]


@track_failures("roadmaps")
class ListingService:
    """Business rules for the private dashboard and the public profile."""

    def __init__(
        self,
        repo: RoadmapRepository,
        *,
        handle_resolver: HandleResolver,
        followed_reader: FollowedReader,
    ) -> None:
        self._repo = repo
        # Resolves a handle to its owner for the public profile; injected so the
        # roadmaps domain never imports the accounts repository into its logic.
        self._handle_resolver = handle_resolver
        # Resolves the caller's followed roadmap ids for the dashboard; injected
        # the same way so roadmaps stays decoupled from the progress domain.
        self._followed_reader = followed_reader

    async def dashboard(self, user_id: str) -> Dashboard:
        """The caller's private dashboard: authored (any status) + followed.

        Owner-scoped: ``authored`` is every roadmap the caller owns and
        ``followed`` is every roadmap they follow (resolved from their own
        progress rows), so no other user's data is exposed. A roadmap the caller
        both authored and follows appears in both lists (spec section 02
        US-ACCT-03)."""
        authored = await self._repo.list_owned(user_id)
        followed = await self._load_followed(user_id)
        return Dashboard(
            authored=[_to_card(record) for record in authored],
            followed=followed,
        )

    async def profile(self, handle: str) -> Profile:
        """The public profile for ``handle``: published-public roadmaps only.

        An unknown handle is a 404. The listing is
        viewer-agnostic and excludes every non-published-public roadmap at the
        query level, so a profile never leaks a draft, private, or archived
        roadmap, nor who follows what."""
        owner = await self._handle_resolver(handle)
        if owner is None:
            raise NotFound(f"No profile for handle '{handle}'.", instance=f"/users/{handle}")
        published_public = await self._repo.list_published_public(owner.user_id)
        return Profile(
            handle=owner.handle,
            display_name=owner.display_name,
            roadmaps=[_to_card(record) for record in published_public],
        )

    async def _load_followed(self, user_id: str) -> list[RoadmapCard]:
        """Load the caller's followed roadmaps as cards, in follow order.

        Preserves the order the follow reader returns (most-recently-updated
        first) and skips any id without a live roadmap record defensively."""
        followed_ids = await self._followed_reader(user_id)
        records = await self._repo.list_by_ids(followed_ids)
        by_id = {record.id: record for record in records}
        return [_to_card(by_id[rid]) for rid in followed_ids if rid in by_id]


def _to_card(record: RoadmapRecord) -> RoadmapCard:
    """Project a stored roadmap row into its list-card shape.

    Reads ``subject_tags`` from the authoritative document (the scalar index has
    no tags column); ``status`` / ``visibility`` come off the validated document
    as the domain enums so the response carries the same values the badges use."""
    roadmap = Roadmap.model_validate(record.document)
    return RoadmapCard(
        id=roadmap.id,
        title=roadmap.title,
        status=roadmap.status,
        visibility=roadmap.visibility,
        subject_tags=list(roadmap.subject_tags),
    )
