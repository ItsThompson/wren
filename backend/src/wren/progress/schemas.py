"""Progress data model + wire projections (spec sections 04, 07).

Progress is the second top-level entity (spec section 04): one mutable record per
``(user_id, roadmap_id)``, holding the explicit-set ``checked`` map and an
optional per-user ``deadline``. It is stored separately from the roadmap
definition (one roadmap : many progress records) and is always private to its
user.

The derived read projections (``ProgressSnapshot`` / ``SectionProgress``) and the
server-computed ``NextResult`` are never stored: they are recomputed from the
roadmap + progress on each read (spec section 04 "Derived"). The richer
``NextResult`` fields (``why_now`` / ``remaining_in_path`` / ``path_position``)
and the ``deadline`` write land in Ticket 17; this slice keeps the minimal shape.

These Pydantic models are the single source of truth for the wire contract; the
frontend consumes them as OpenAPI-generated TypeScript (spec sections 06/10).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from wren.roadmaps.schemas import ResourceType


class CompletionState(StrEnum):
    """The explicit target state a ``progress_update`` sets its items to.

    Explicit set, never toggle (spec section 07): the client states the desired
    state so a retry is idempotent.
    """

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


# ---------- Progress (mutable, one record per (user, roadmap)) ----------


class Progress(BaseModel):
    """A user's progress against one roadmap (spec section 04).

    ``checked`` maps a checklist-item id to its checked state; only checked items
    are retained (an unchecked item is simply absent), which keeps the map lean
    and the explicit-set idempotent. ``user_id`` is resolved from the
    token/session and never trusted from args. This is the ``follow`` response
    body (following creates the record)."""

    user_id: str
    roadmap_id: str
    deadline: date | None = None
    checked: dict[str, bool] = Field(default_factory=dict)
    updated_at: datetime


# ---------- Derived read projections (computed, never stored) ----------


class SectionProgress(BaseModel):
    """Per-section completion counts, derived from progress + roadmap."""

    section_id: str
    total_items: int
    checked_items: int
    percent: int


class ProgressSnapshot(BaseModel):
    """The ``GET /progress`` body: roadmap-wide + per-section completion.

    ``checked_ids`` is populated only in ``detailed`` mode (spec section 04),
    keeping the default concise response small while still letting a client
    reconcile the exact checked set when it asks for it."""

    roadmap_id: str
    total_items: int
    checked_items: int
    percent: int
    deadline: date | None = None
    sections: list[SectionProgress] = Field(default_factory=list)
    checked_ids: list[str] | None = None


# ---------- Server-computed next (spec section 07 get_next) ----------


class ResourceLink(BaseModel):
    """A resource reference on a next item: a link, never an inlined body."""

    title: str
    url: str
    type: ResourceType


class NextItem(BaseModel):
    """One unchecked, prereq-satisfied checklist item to work on next.

    The richer ``why_now`` / ``path_position`` fields land in Ticket 17 (spec
    section 07); this slice returns the item, its subsection, and the resource
    links for it."""

    subsection_id: str
    item_id: str
    text: str
    resources: list[ResourceLink] = Field(default_factory=list)


class NextResult(BaseModel):
    """The ``GET /next`` body: the next unchecked items in ``suggested_path``
    order whose prerequisites are all complete, plus a ``complete`` flag that is
    ``True`` when nothing remains (spec section 07). ``remaining_in_path`` lands
    in Ticket 17."""

    items: list[NextItem] = Field(default_factory=list)
    complete: bool = False


# ---------- Requests + write result ----------


class ProgressUpdateRequest(BaseModel):
    """The ``POST /progress`` body: set ``item_ids`` to ``state`` (explicit set,
    not toggle; spec section 07). At least one id is required so an update is
    never a silent no-op. The optional per-user ``deadline`` write lands in
    Ticket 17."""

    item_ids: list[str] = Field(min_length=1)
    state: CompletionState


class ProgressUpdateResult(BaseModel):
    """The ``POST /progress`` body: the fresh snapshot after the set plus the
    next suggestion (spec sections 04/07). The snapshot is returned in detailed
    mode so the client can reconcile its checkbox state to the server truth."""

    progress: ProgressSnapshot
    next: NextResult
