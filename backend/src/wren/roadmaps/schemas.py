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
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from wren.core.errors import Conflict, ErrorCode, Violation


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


class VisibilityRequest(BaseModel):
    """The ``PUT /roadmaps/{id}/visibility`` body: toggle public/private (web-only,
    spec sections 04/06).

    Visibility is a lifecycle/presentation field, editable by the owner on a
    roadmap of any status (draft or published): a public roadmap is reachable by
    link and appears on the owner's profile, a private one is owner-only. The
    toggle is last-write-wins (never ``If-Match``-guarded) and touches no
    follower-visible structure, so it never bumps the structural ``revision``.
    """

    visibility: Visibility


class MetadataEditRequest(BaseModel):
    """The ``PATCH /roadmaps/{id}/metadata`` body: the presentation-only fields
    that stay mutable after publish (spec sections 04/06).

    Only ``title`` / ``description`` / ``subject_tags`` are editable here; a field
    left out (``None``) is unchanged (last-write-wins, deliberately not
    ``If-Match``-guarded and never bumps the structural ``revision``). ``extra`` is
    ``allow``ed so a smuggled structural, lifecycle, or identity field (e.g.
    ``sections`` / ``visibility`` / ``status`` / ``revision``) is *captured* rather
    than silently dropped, then rejected as immutable by
    :meth:`reject_structural_fields`: the metadata endpoint can never touch
    anything but presentation."""

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    description: str | None = None
    subject_tags: list[str] | None = None

    def reject_structural_fields(self) -> None:
        """Raise ``Conflict`` (409 ``IMMUTABLE``) if any non-presentation field was
        sent, naming the offending fields and pointing to the sanctioned paths.

        This is what makes the endpoint presentation-only at the wire boundary: a
        client cannot smuggle a content, visibility, status, or revision change
        through the metadata edit. Presentation edits stay allowed post-publish;
        structural changes require a draft (fork a published roadmap first)."""
        smuggled = sorted(self.model_extra or {})
        if smuggled:
            fields = ", ".join(smuggled)
            raise Conflict(
                f"Fields are immutable via the metadata endpoint: {fields}. Only title, "
                "description, and subject_tags are editable here; change structure on a draft "
                "(fork a published roadmap to make structural changes).",
                code=ErrorCode.IMMUTABLE,
            )


# ---------- Responses ----------


class RoadmapCreated(Roadmap):
    """The ``POST /roadmaps`` body: the full minted roadmap plus a ``remap`` of
    every de-duped ``proposed_id -> minted_id`` so the author can reconcile the
    references it sent (spec section 04). ``remap`` is empty when no proposed ID
    had to be changed."""

    remap: dict[str, str] = Field(default_factory=dict)


class RoadmapReplaced(Roadmap):
    """The ``PUT /roadmaps/{id}`` body: the full rebuilt draft after a full-document
    import (the escape hatch, spec section 07) plus the ``proposed_id -> minted_id``
    remap. Mirrors :class:`RoadmapCreated` because replace reuses the same
    mint-then-resolve assembly: ``proposed_id``s are preserved, every other node is
    re-minted, and the roadmap's own ID is unchanged (spec section 04). ``remap`` is
    empty when no proposed ID had to be de-duped."""

    remap: dict[str, str] = Field(default_factory=dict)


class ValidateResult(BaseModel):
    """The ``POST /roadmaps/{id}:validate`` body: all structural violations in one
    pass (empty when the draft is publishable). The ``violations`` shape is
    identical to the 422 publish hard-block body (spec section 06), so a client
    handles one violation contract for both validate and publish."""

    violations: list[Violation] = Field(default_factory=list)


# ---------- Patch operations (spec section 07 grammar) ----------
#
# The canonical single-dispatch iterative-edit surface: an ``operations[]`` array
# applied atomically (spec section 07). Every op addresses nodes by slug ID (never
# array index); ordering is expressed with ``before_id``/``after_id`` (never an
# array resend). The ``op`` string is the Pydantic discriminator, so the union
# is parsed unambiguously and surfaces to the frontend as an OpenAPI ``oneOf``.
# ``add_*`` ops accept an optional ``proposed_id`` (carried directly on
# ``add_item``/``add_section`` and via the nested ``*Input`` on
# ``add_subsection``/``set_resources``); the applier mints one otherwise and
# echoes a ``proposed_id -> minted_id`` remap for any it had to de-dupe.


class AddSubsectionOp(BaseModel):
    op: Literal["add_subsection"]
    section_id: str
    subsection: SubsectionInput
    before_id: str | None = None
    after_id: str | None = None


class UpdateSubsectionOp(BaseModel):
    op: Literal["update_subsection"]
    subsection_id: str
    title: str | None = None
    description: str | None = None
    effort_estimate: str | None = None


class RemoveSubsectionOp(BaseModel):
    op: Literal["remove_subsection"]
    subsection_id: str


class AddEdgeOp(BaseModel):
    """``to_id`` gains ``from_id`` as a prerequisite (spec section 07)."""

    op: Literal["add_edge"]
    from_id: str
    to_id: str


class RemoveEdgeOp(BaseModel):
    op: Literal["remove_edge"]
    from_id: str
    to_id: str


class SetTagsOp(BaseModel):
    op: Literal["set_tags"]
    subsection_id: str
    tags: list[str] = Field(default_factory=list)


class SetResourcesOp(BaseModel):
    op: Literal["set_resources"]
    subsection_id: str
    resources: list[ResourceInput] = Field(default_factory=list)


class SetEffortOp(BaseModel):
    op: Literal["set_effort"]
    subsection_id: str
    effort_estimate: str | None = None


class AddItemOp(BaseModel):
    op: Literal["add_item"]
    subsection_id: str
    text: str
    proposed_id: str | None = None
    before_id: str | None = None
    after_id: str | None = None


class UpdateItemOp(BaseModel):
    op: Literal["update_item"]
    item_id: str
    text: str


class RemoveItemOp(BaseModel):
    op: Literal["remove_item"]
    item_id: str


class ReorderOp(BaseModel):
    """Move any node (section / subsection / item) within its sibling order."""

    op: Literal["reorder"]
    target_id: str
    before_id: str | None = None
    after_id: str | None = None


class SetSuggestedPathOp(BaseModel):
    op: Literal["set_suggested_path"]
    path: list[str] = Field(default_factory=list)


class AddSectionOp(BaseModel):
    op: Literal["add_section"]
    title: str
    proposed_id: str | None = None
    before_id: str | None = None
    after_id: str | None = None


class UpdateSectionOp(BaseModel):
    op: Literal["update_section"]
    section_id: str
    title: str


class RemoveSectionOp(BaseModel):
    op: Literal["remove_section"]
    section_id: str


PatchOp = Annotated[
    AddSubsectionOp
    | UpdateSubsectionOp
    | RemoveSubsectionOp
    | AddEdgeOp
    | RemoveEdgeOp
    | SetTagsOp
    | SetResourcesOp
    | SetEffortOp
    | AddItemOp
    | UpdateItemOp
    | RemoveItemOp
    | ReorderOp
    | SetSuggestedPathOp
    | AddSectionOp
    | UpdateSectionOp
    | RemoveSectionOp,
    Field(discriminator="op"),
]


class PatchRequest(BaseModel):
    """The ``PATCH /roadmaps/{id}`` body: the ordered op list applied atomically.

    The target ``revision`` travels in the ``If-Match`` header (spec section 06),
    not the body. At least one op is required so a patch is never a silent no-op
    that would still burn a revision.
    """

    operations: list[PatchOp] = Field(min_length=1)


class ChangedNodeKind(StrEnum):
    ROADMAP = "roadmap"
    SECTION = "section"
    SUBSECTION = "subsection"
    ITEM = "item"


class ChangeType(StrEnum):
    ADDED = "added"
    UPDATED = "updated"
    REMOVED = "removed"


class ChangedNode(BaseModel):
    """One node the batch touched, echoed back so the agent knows what changed
    without re-reading the whole roadmap (spec section 07: summary-first). Lean
    on purpose (kind + id + change), keeping a small edit's response near the
    ~50-token target; the agent re-reads a specific node for its new body."""

    kind: ChangedNodeKind
    id: str
    change: ChangeType


class PatchResult(BaseModel):
    """The ``PATCH /roadmaps/{id}`` body: the post-batch ``revision``, the changed
    nodes, and the ``proposed_id -> minted_id`` remap for any de-duped ``add_*``
    proposal (spec section 07). ``remap`` is empty when nothing was de-duped."""

    roadmap_id: str
    revision: int
    changed_nodes: list[ChangedNode] = Field(default_factory=list)
    remap: dict[str, str] = Field(default_factory=dict)
