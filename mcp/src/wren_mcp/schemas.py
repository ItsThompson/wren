"""MCP write-tool contract schemas (frozen; spec sections 04/07/13).

The MCP server is a separate image with no backend-code dependency, so the
authoring wire shapes are re-declared here as the **frozen MCP contract** (the
same "duplicated domain truth kept in sync by contract" pattern as
:mod:`wren_mcp.config`'s header names). A snapshot test freezes the generated
JSON Schemas so the deliberately-frozen tool contracts cannot drift silently:
the MCP analog of the OpenAPI drift check (spec section 13).

Inputs mirror the backend authoring types (ordered arrays + optional
``proposed_id``, key-addressed, never index-addressed). Outputs are **lean**
projections (spec section 07: summary-first, within MCP token guidance): a small
``patch`` returns ~50 tokens of changed-node ids, and ``create``/``replace``
return identity + the ``proposed_id -> minted_id`` remap rather than the whole
document. ``visibility`` is intentionally absent from the authoring inputs:
visibility is a web-only lifecycle control with no agent tool (spec section 07).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class ResourceType(StrEnum):
    ARTICLE = "article"
    VIDEO = "video"
    BOOK = "book"
    COURSE = "course"
    DOCS = "docs"
    OTHER = "other"


class RoadmapStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


# ---------- Authoring inputs (ordered arrays + optional proposed_id) ----------


class ResourceInput(BaseModel):
    """An external link on a subsection; the body is never inlined (spec 07)."""

    proposed_id: str | None = None
    title: str
    url: str
    type: ResourceType


class ChecklistItemInput(BaseModel):
    proposed_id: str | None = None
    text: str


class SubsectionInput(BaseModel):
    """A DAG node. Child collections are ordered arrays because IDs are
    server-minted; ``prereq_ids`` may reference sibling ``proposed_id``s."""

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


class RoadmapDraftInput(BaseModel):
    """The full-document payload for ``create_roadmap_draft`` and
    ``replace_roadmap_draft`` (spec section 04 ``RoadmapInput``)."""

    proposed_id: str | None = None
    title: str
    description: str | None = None
    subject_tags: list[str] = Field(default_factory=list)
    sections: list[SectionInput] = Field(default_factory=list)
    suggested_path: list[str] = Field(default_factory=list)


# ---------- Patch operation grammar (spec section 07, canonical dispatch) ------
#
# One ``operations[]`` array applied atomically. Every op is key-addressed by
# slug ID; ordering uses ``before_id``/``after_id`` (never an array resend). The
# ``op`` literal is the Pydantic discriminator, so the union parses unambiguously
# and renders as a discriminated ``oneOf`` in the frozen schema. ``add_*`` ops
# accept an optional ``proposed_id`` (directly on ``add_item``/``add_section``,
# via the nested ``*Input`` on ``add_subsection``/``set_resources``); the server
# mints one otherwise and echoes a ``proposed_id -> minted_id`` remap on de-dup.


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


# ---------- Lean output projections ----------


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
    """One node a patch touched, echoed back so the agent knows what changed
    without re-reading the whole roadmap (spec section 07: summary-first)."""

    kind: ChangedNodeKind
    id: str
    change: ChangeType


class Violation(BaseModel):
    """One structural rule failure, model-recoverable by naming the rule + IDs."""

    rule: str
    ids: list[str] = Field(default_factory=list)
    message: str


class CreatedRoadmap(BaseModel):
    """``create_roadmap_draft`` result: the minted ``roadmap_id`` plus the
    ``proposed_id -> minted_id`` remap for any de-duped proposal. Supply
    ``proposed_id`` on the nodes you intend to reference; preserved IDs need no
    remap entry, so this stays lean."""

    roadmap_id: str
    revision: int
    status: RoadmapStatus
    remap: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_backend(cls, body: dict[str, Any]) -> CreatedRoadmap:
        return cls(
            roadmap_id=body["id"],
            revision=body["revision"],
            status=RoadmapStatus(body["status"]),
            remap=body.get("remap", {}),
        )


class ReplacedRoadmap(BaseModel):
    """``replace_roadmap_draft`` result: the roadmap ID is unchanged; every node
    without a preserved ``proposed_id`` is re-minted, echoed via ``remap``."""

    roadmap_id: str
    revision: int
    status: RoadmapStatus
    remap: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_backend(cls, body: dict[str, Any]) -> ReplacedRoadmap:
        return cls(
            roadmap_id=body["id"],
            revision=body["revision"],
            status=RoadmapStatus(body["status"]),
            remap=body.get("remap", {}),
        )


class PatchResult(BaseModel):
    """``patch_roadmap_draft`` result: the post-batch ``revision`` (pass it as the
    next call's ``revision``), the changed nodes, and the ``proposed_id ->
    minted_id`` remap for any de-duped ``add_*`` proposal."""

    roadmap_id: str
    revision: int
    changed_nodes: list[ChangedNode] = Field(default_factory=list)
    remap: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_backend(cls, body: dict[str, Any]) -> PatchResult:
        return cls(
            roadmap_id=body["roadmap_id"],
            revision=body["revision"],
            changed_nodes=[
                ChangedNode.model_validate(node) for node in body.get("changed_nodes", [])
            ],
            remap=body.get("remap", {}),
        )


class ValidationResult(BaseModel):
    """``validate_roadmap_draft`` result: every structural violation in one pass.
    ``publishable`` is true exactly when ``violations`` is empty (spec 06/07)."""

    publishable: bool
    violations: list[Violation] = Field(default_factory=list)

    @classmethod
    def from_backend(cls, body: dict[str, Any]) -> ValidationResult:
        violations = [Violation.model_validate(item) for item in body.get("violations", [])]
        return cls(publishable=not violations, violations=violations)


class PublishResult(BaseModel):
    """``publish_roadmap`` result: the roadmap after the one-way draft->published
    transition."""

    roadmap_id: str
    revision: int
    status: RoadmapStatus

    @classmethod
    def from_backend(cls, body: dict[str, Any]) -> PublishResult:
        return cls(
            roadmap_id=body["id"],
            revision=body["revision"],
            status=RoadmapStatus(body["status"]),
        )


class ForkResult(BaseModel):
    """``fork_roadmap`` result: a fresh draft seeded from the source with new IDs
    and fresh progress; ``source_roadmap_id`` echoes what was forked."""

    roadmap_id: str
    revision: int
    status: RoadmapStatus
    source_roadmap_id: str

    @classmethod
    def from_backend(cls, body: dict[str, Any], *, source_roadmap_id: str) -> ForkResult:
        return cls(
            roadmap_id=body["id"],
            revision=body["revision"],
            status=RoadmapStatus(body["status"]),
            source_roadmap_id=source_roadmap_id,
        )


class MetadataResult(BaseModel):
    """``edit_roadmap_metadata`` result: the presentation fields after the edit
    (allowed on published roadmaps; never touches structure or ``revision``)."""

    roadmap_id: str
    title: str
    description: str | None = None
    subject_tags: list[str] = Field(default_factory=list)

    @classmethod
    def from_backend(cls, body: dict[str, Any]) -> MetadataResult:
        return cls(
            roadmap_id=body["id"],
            title=body["title"],
            description=body.get("description"),
            subject_tags=body.get("subject_tags", []),
        )
