"""Roadmap list projections for the dashboard + public profile (spec sections 06, 09).

These are the compact card projections the two list views consume, **not** the
full :class:`~wren.roadmaps.schemas.Roadmap`: a :class:`RoadmapCard` carries only
what a card needs (title, status/visibility badges, subject tags), the private
:class:`Dashboard` groups the caller's authored and followed roadmaps, and the
public :class:`Profile` carries a handle's published-public roadmaps.

Defined once here as Pydantic models (the single source of truth for the wire
contract) and surfaced to the frontend as OpenAPI-generated TypeScript (spec
sections 06/10). The card deliberately omits per-user progress: the dashboard
shows status badges and the profile is a viewer-agnostic
public page, so neither leaks who follows what.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from wren.roadmaps.schemas import RoadmapStatus, Visibility


class RoadmapCard(BaseModel):
    """A roadmap summarized for a list/grid card.

    ``status`` drives the Draft/Published/Archived badge and ``visibility`` the
    lock/globe badge. Content (sections, items, progress)
    is never inlined: a card links to the full roadmap view for that."""

    id: str
    title: str
    status: RoadmapStatus
    visibility: Visibility
    subject_tags: list[str] = Field(default_factory=list)


class Dashboard(BaseModel):
    """The ``GET /me/dashboard`` body: the caller's private home (spec section 02
    US-ACCT-03).

    ``authored`` is everything the caller owns at any status (draft / private /
    public), rendered in the "Yours" section; ``followed`` is every roadmap the
    caller follows, rendered in the "Following" section. A
    roadmap the caller both authored and follows appears in both lists. Scoped to
    the caller: another user's dashboard is never returned."""

    authored: list[RoadmapCard] = Field(default_factory=list)
    followed: list[RoadmapCard] = Field(default_factory=list)


class Profile(BaseModel):
    """The ``GET /users/{handle}`` body: a user's public profile (spec section 02
    US-ACCT-03).

    ``roadmaps`` is only that user's **published, public** roadmaps; drafts,
    private, and archived roadmaps never appear, and following is never exposed
    (no social graph). Public and viewer-agnostic: the same body regardless of who
    (if anyone) is signed in."""

    handle: str
    display_name: str
    roadmaps: list[RoadmapCard] = Field(default_factory=list)
