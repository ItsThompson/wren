"""Typed read projections for the study-time read surface.

These are the purpose-built projections the read endpoints/tools return, **not**
the full :class:`~wren.roadmaps.schemas.Roadmap`: an orientation ``Overview``, a
single-node ``NodeDetail``, a paginated ``SectionPage``, and ``SearchHit``s. They
are defined once here as Pydantic models (the single source of truth for the wire
contract) and surfaced to the frontend as OpenAPI-generated TypeScript; the MCP
read tools are thin calls over the same
shapes, one HTTP call each.

Design rules they encode:

- **Summary-first, then drill-down.** ``Overview`` carries per-section counts and
  no checklist-item bodies; ``NodeDetail`` is the drill-down.
- **Resource links, never inlined bodies.** ``ResourceRef`` is a link (``url``),
  never the article/video content.
- **``concise | detailed``.** The concise projection (default) omits the verbose
  node ``description`` while still carrying every ID needed for a follow-up call;
  detailed adds it (see :func:`wren.roadmaps.projections.build_node_detail`).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from wren.roadmaps.schemas import ResourceType, RoadmapStatus


class ResponseFormat(StrEnum):
    """The ``concise | detailed`` switch on the read tools.

    Concise is roughly one-third the tokens and still carries the follow-up IDs;
    detailed adds the explanatory free-text (the node ``description``)."""

    CONCISE = "concise"
    DETAILED = "detailed"


class SectionInclude(StrEnum):
    """Which parts of each node a ``SectionPage`` populates.

    ``subsections`` = node metadata (tags, effort, resources, resolved prereqs);
    ``items`` = the checklist items only; ``both`` = everything. Every variant
    still carries the ``subsection_id`` so the agent can drill in further."""

    SUBSECTIONS = "subsections"
    ITEMS = "items"
    BOTH = "both"


class SearchHitKind(StrEnum):
    """Whether a search hit is a subsection (DAG node) or a checklist item."""

    SUBSECTION = "subsection"
    ITEM = "item"


# ---------- NodeDetail (roadmap_get_node / the paginated section body) ----------


class ResourceRef(BaseModel):
    """A subsection resource as a link, never an inlined body."""

    id: str
    title: str
    url: str
    type: ResourceType


class PrereqRef(BaseModel):
    """A resolved prerequisite: its id, title, and the caller's done state.

    ``done`` is ``True`` when the caller has completed every checklist item of the
    prerequisite subsection (so an agent can see at a glance whether this node is
    unlocked)."""

    id: str
    title: str
    done: bool


class ItemState(BaseModel):
    """A checklist item with the caller's done state (``done`` = checked)."""

    id: str
    text: str
    done: bool


class NodeDetail(BaseModel):
    """One subsection resolved for study.

    ``description`` is populated only in ``detailed`` mode; the concise projection
    leaves it ``None`` while still carrying every follow-up ID (the subsection id,
    the resource links, the resolved prereq ids, and the item ids). External
    bodies are never inlined: ``resources`` are links only."""

    subsection_id: str
    title: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    effort_estimate: str | None = None
    resources: list[ResourceRef] = Field(default_factory=list)
    prereqs: list[PrereqRef] = Field(default_factory=list)
    items: list[ItemState] = Field(default_factory=list)


# ---------- Overview (roadmap_get_overview) ----------


class SectionOverview(BaseModel):
    """Per-section completion counts, no checklist-item bodies."""

    section_id: str
    title: str
    total_items: int
    checked_items: int
    percent: int


class OverallProgress(BaseModel):
    """Roadmap-wide completion totals (derived, never stored)."""

    total_items: int
    checked_items: int
    percent: int


class Overview(BaseModel):
    """The ``GET /overview`` body: sections in ``section_order`` with per-section
    and overall completion, and no checklist-item bodies.

    The orientation call; from here the agent drills into a node (``get_node``) or
    a section (``get_section``). ``checked_items`` / ``percent`` reflect the
    caller's own progress (zero when they have not started)."""

    roadmap_id: str
    title: str
    status: RoadmapStatus
    revision: int
    sections: list[SectionOverview] = Field(default_factory=list)
    overall: OverallProgress


# ---------- SectionPage (roadmap_get_section, paginated) ----------


class SectionPage(BaseModel):
    """The ``GET /sections/{sid}`` body: a paginated section drill-down.

    ``include`` selects which parts of each node are populated. The page holds a
    server-set number of subsections in ``subsection_order``; ``next_cursor`` is
    an **opaque** token for the next page (absent on the last page) and
    ``steering`` is present only when the response was truncated."""

    section_id: str
    title: str
    include: SectionInclude
    subsections: list[NodeDetail] = Field(default_factory=list)
    next_cursor: str | None = None
    steering: str | None = None


# ---------- SearchHit (roadmap_search) ----------


class SearchHit(BaseModel):
    """One search match, carrying the IDs needed to drill down.

    ``item_id`` is present only when ``kind == item``; ``matched_tags`` names the
    subsection tags that matched a tag filter (absent for a keyword-only match)."""

    kind: SearchHitKind
    subsection_id: str
    item_id: str | None = None
    title_or_text: str
    matched_tags: list[str] | None = None
