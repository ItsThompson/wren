"""MCP write-tool contract schemas.

The MCP server ships as a separate image with no backend-code dependency, so the
agent-facing types are re-declared here rather than imported from ``wren``. The
Group-A types (shared enums, authoring inputs, the 16 patch ops, ``ChangedNode``,
``Violation``, and the read projections) are GENERATED from the internal app's
OpenAPI document into :mod:`wren_mcp._schemas_generated` (see ``just codegen-mcp``
and docs/adr/0001-*), so field drift against the backend is structurally
impossible. This module re-exports them and hand-authors the parts that are not a
field-for-field backend mirror:

* ``PatchOp``: the discriminated union alias over the generated op members. The
  generator emits a top-level ``oneOf`` as a ``RootModel`` subclass, not the
  ``Annotated[..., Field(discriminator="op")]`` alias ``tools_write`` and the
  frozen tool snapshot use, so the alias is declared here over the generated
  member classes.
* **Group B** lean write results (``CreatedRoadmap``, ``ReplacedRoadmap``,
  ``PatchResult``, ``ValidationResult``, ``PublishResult``, ``ForkResult``,
  ``MetadataResult``): token-optimized agent projections that deliberately expose
  fewer fields than the backend results, each with a ``from_backend`` adapter.
* **Group C** ``SearchResults``: the MCP-only structured wrapper around the hit
  list.

``visibility`` is web-only, so the authoring input carries no such field (the
generator drops it and prunes the orphaned ``Visibility`` enum). Enforced by the
tool schema snapshot and the cross-package ``contract-drift`` mirror test
(``contract/tests/test_schema_mirror.py``).
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field

from wren_mcp._schemas_generated import (
    AddEdgeOp,
    AddItemOp,
    AddSectionOp,
    AddSubsectionOp,
    ChangedNode,
    ChangedNodeKind,
    ChangeType,
    ChecklistItemInput,
    CompletionState,
    ItemState,
    NextItem,
    NextResult,
    NodeDetail,
    OverallProgress,
    Overview,
    PrereqRef,
    ProgressSnapshot,
    ProgressUpdateResult,
    RemoveEdgeOp,
    RemoveItemOp,
    RemoveSectionOp,
    RemoveSubsectionOp,
    ReorderOp,
    ResourceInput,
    ResourceLink,
    ResourceRef,
    ResourceType,
    ResponseFormat,
    RoadmapDraftInput,
    RoadmapStatus,
    SearchHit,
    SearchHitKind,
    SectionInclude,
    SectionInput,
    SectionOverview,
    SectionPage,
    SectionProgress,
    SetEffortOp,
    SetResourcesOp,
    SetSuggestedPathOp,
    SetTagsOp,
    SubsectionInput,
    UpdateItemOp,
    UpdateSectionOp,
    UpdateSubsectionOp,
    Violation,
)

# ---------- Patch operation grammar (canonical dispatch) ----------------------
#
# The discriminated union over the 16 generated op members, keyed by the ``op``
# literal. Hand-authored (not generated) because the generator emits a top-level
# ``oneOf`` component as a ``RootModel`` subclass, which would change the tool
# input schema at every ``list[PatchOp]`` use site. The member order mirrors the
# backend union so the generated tool schema's ``oneOf`` order is unchanged.
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


# ---------- Group B: lean output projections (hand-authored) ------------------


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
    ``publishable`` is true exactly when ``violations`` is empty."""

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


# ---------- Group C: MCP-only structured wrapper ------------------------------


class SearchResults(BaseModel):
    """``roadmap_search`` result: the matching hits (search, not list-all).

    A thin object wrapper around the hit list so the tool returns a structured
    ``outputSchema`` object like every other tool (rather than a bare array)."""

    hits: list[SearchHit] = Field(default_factory=list)


# The public contract surface: the generated Group-A types (re-exported), the
# hand-authored ``PatchOp`` union, the Group-B lean write results, and the
# Group-C wrapper. Declared explicitly so re-exports are unambiguous under
# ``mypy --strict`` (no implicit re-export).
__all__ = [
    "AddEdgeOp",
    "AddItemOp",
    "AddSectionOp",
    "AddSubsectionOp",
    "ChangeType",
    "ChangedNode",
    "ChangedNodeKind",
    "ChecklistItemInput",
    "CompletionState",
    "CreatedRoadmap",
    "ForkResult",
    "ItemState",
    "MetadataResult",
    "NextItem",
    "NextResult",
    "NodeDetail",
    "OverallProgress",
    "Overview",
    "PatchOp",
    "PatchResult",
    "PrereqRef",
    "ProgressSnapshot",
    "ProgressUpdateResult",
    "PublishResult",
    "RemoveEdgeOp",
    "RemoveItemOp",
    "RemoveSectionOp",
    "RemoveSubsectionOp",
    "ReorderOp",
    "ReplacedRoadmap",
    "ResourceInput",
    "ResourceLink",
    "ResourceRef",
    "ResourceType",
    "ResponseFormat",
    "RoadmapDraftInput",
    "RoadmapStatus",
    "SearchHit",
    "SearchHitKind",
    "SearchResults",
    "SectionInclude",
    "SectionInput",
    "SectionOverview",
    "SectionPage",
    "SectionProgress",
    "SetEffortOp",
    "SetResourcesOp",
    "SetSuggestedPathOp",
    "SetTagsOp",
    "SubsectionInput",
    "UpdateItemOp",
    "UpdateSectionOp",
    "UpdateSubsectionOp",
    "ValidationResult",
    "Violation",
]
