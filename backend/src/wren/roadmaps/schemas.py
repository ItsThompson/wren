"""Roadmap data model + authoring input types (spec section 04).

The persisted shape is ID-keyed maps plus explicit ``*_order`` arrays (the EASE
model), so operations are order-invariant and no contract ever addresses a node
by array index. The ``*Input`` types are the authoring surface: because IDs are
server-minted, their child collections are **ordered arrays** (array order
becomes the persisted ``*_order``) and each node may carry an optional
``proposed_id`` so an agent can reference it within the same payload.

These Pydantic models are the single source of truth for the wire contract; the
frontend consumes them as OpenAPI-generated TypeScript (spec sections 06/10).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RoadmapStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class ResourceType(StrEnum):
    ARTICLE = "article"
    VIDEO = "video"
    BOOK = "book"
    COURSE = "course"
    DOCS = "docs"
    OTHER = "other"


# ---------- Roadmap (definition) ----------


class Resource(BaseModel):
    """An external link on a subsection; the body is never inlined."""

    id: str
    title: str
    url: str
    type: ResourceType


class ChecklistItem(BaseModel):
    """The only checkable unit."""

    id: str
    text: str


class Subsection(BaseModel):
    """The DAG node: track tags, resources, checklist items, prereq edges."""

    id: str
    title: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    effort_estimate: str | None = None
    prereq_ids: list[str] = Field(default_factory=list)
    resources: dict[str, Resource] = Field(default_factory=dict)
    resource_order: list[str] = Field(default_factory=list)
    checklist_items: dict[str, ChecklistItem] = Field(default_factory=dict)
    item_order: list[str] = Field(default_factory=list)


class Section(BaseModel):
    """An ordered phase grouping DAG-node subsections."""

    id: str
    title: str
    subsections: dict[str, Subsection] = Field(default_factory=dict)
    subsection_order: list[str] = Field(default_factory=list)


class Roadmap(BaseModel):
    """A roadmap definition owned by one user. ``owner`` is resolved from the
    session, never trusted from client input."""

    id: str
    owner: str
    title: str
    description: str | None = None
    subject_tags: list[str] = Field(default_factory=list)
    visibility: Visibility = Visibility.PRIVATE
    status: RoadmapStatus = RoadmapStatus.DRAFT
    revision: int = 1
    sections: dict[str, Section] = Field(default_factory=dict)
    section_order: list[str] = Field(default_factory=list)
    suggested_path: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ---------- Authoring input (ordered arrays + optional proposed_id) ----------


class ResourceInput(BaseModel):
    proposed_id: str | None = None
    title: str
    url: str
    type: ResourceType


class ChecklistItemInput(BaseModel):
    proposed_id: str | None = None
    text: str


class SubsectionInput(BaseModel):
    proposed_id: str | None = None
    title: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    effort_estimate: str | None = None
    prereq_ids: list[str] = Field(default_factory=list)
    resources: list[ResourceInput] = Field(default_factory=list)
    checklist_items: list[ChecklistItemInput] = Field(default_factory=list)


class SectionInput(BaseModel):
    proposed_id: str | None = None
    title: str
    subsections: list[SubsectionInput] = Field(default_factory=list)


class RoadmapInput(BaseModel):
    """The ``create_roadmap_draft`` / ``replace_roadmap_draft`` payload."""

    proposed_id: str | None = None
    title: str
    description: str | None = None
    subject_tags: list[str] = Field(default_factory=list)
    visibility: Visibility = Visibility.PRIVATE
    sections: list[SectionInput] = Field(default_factory=list)
    suggested_path: list[str] = Field(default_factory=list)


# ---------- Responses ----------


class RoadmapCreated(Roadmap):
    """The ``POST /roadmaps`` body: the full minted roadmap plus a ``remap`` of
    every de-duped ``proposed_id -> minted_id`` so the author can reconcile the
    references it sent (spec section 04). ``remap`` is empty when no proposed ID
    had to be changed."""

    remap: dict[str, str] = Field(default_factory=dict)
