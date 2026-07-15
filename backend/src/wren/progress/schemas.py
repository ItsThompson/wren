"""Progress data model + wire projections.

Progress is the second top-level entity: one mutable record per
``(user_id, roadmap_id)``, holding the explicit-set ``checked`` map and an
optional per-user ``deadline``. It is stored separately from the roadmap
definition (one roadmap : many progress records) and is always private to its
user.

The derived read projections (``ProgressSnapshot`` / ``SectionProgress``) and the
server-computed ``NextResult`` are never stored: they are recomputed from the
roadmap + progress on each read. ``NextResult`` carries
the full ``get_next`` shape (structural ``why_now``,
``remaining_in_path``, and ``path_position`` under detailed); the per-user
``deadline`` is set/cleared via ``PUT /roadmaps/{id}/deadline`` (:class:`DeadlineRequest`).

These Pydantic models are the single source of truth for the wire contract; the
frontend consumes them as OpenAPI-generated TypeScript.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from wren.roadmaps.schemas import ResourceType


class CompletionState(StrEnum):
    """The explicit target state a ``progress_update`` sets its items to.

    Explicit set, never toggle: the client states the desired
    state so a retry is idempotent.
    """

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


# ---------- Progress (mutable, one record per (user, roadmap)) ----------


class Progress(BaseModel):
    """A user's progress against one roadmap.

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

    ``checked_ids`` is populated only in ``detailed`` mode,
    keeping the default concise response small while still letting a client
    reconcile the exact checked set when it asks for it."""

    roadmap_id: str
    total_items: int
    checked_items: int
    percent: int
    deadline: date | None = None
    sections: list[SectionProgress] = Field(default_factory=list)
    checked_ids: list[str] | None = None


# ---------- Server-computed next (get_next) ----------


class ResourceLink(BaseModel):
    """A resource reference on a next item: a link, never an inlined body."""

    title: str
    url: str
    type: ResourceType


class NextItem(BaseModel):
    """One unchecked, prereq-satisfied checklist item to work on next.

    ``why_now`` is a STRUCTURAL rationale only: it states the
    mechanical facts the app owns (this is the next unchecked subsection in
    ``suggested_path`` and its named prerequisites are complete), never
    pedagogical / ZPD judgement (that intelligence lives in the agent and was
    baked into ``suggested_path`` at authoring time). ``path_position`` (the
    1-based index of the item's subsection in ``suggested_path``) is populated
    only in ``detailed`` mode."""

    subsection_id: str
    item_id: str
    text: str
    why_now: str
    resources: list[ResourceLink] = Field(default_factory=list)
    path_position: int | None = None


class NextResult(BaseModel):
    """The ``GET /next`` body: the next unchecked items in ``suggested_path``
    order whose prerequisites are all complete.

    ``remaining_in_path`` counts the subsections still to do along the path (any
    with an unchecked item); ``complete`` is ``True`` when nothing remains."""

    items: list[NextItem] = Field(default_factory=list)
    remaining_in_path: int = 0
    complete: bool = False


# ---------- Requests + write result ----------


class ProgressUpdateRequest(BaseModel):
    """The ``POST /progress`` body: set ``item_ids`` to ``state`` (explicit set,
    not toggle). At least one id is required so an update is
    never a silent no-op."""

    item_ids: list[str] = Field(min_length=1)
    state: CompletionState


class DeadlineRequest(BaseModel):
    """The ``PUT /roadmaps/{id}/deadline`` body: set or clear the per-user deadline.

    A ``date`` sets the deadline; ``null`` clears it. The deadline is editable and
    clearable at any time. A date in the past is allowed (the countdown shows
    elapsed / overdue with no pacing signal)."""

    deadline: date | None = None


class ProgressUpdateResult(BaseModel):
    """The ``POST /progress`` body: the fresh snapshot after the set plus the
    next suggestion. The snapshot is returned in detailed
    mode so the client can reconcile its checkbox state to the server truth."""

    progress: ProgressSnapshot
    next: NextResult
