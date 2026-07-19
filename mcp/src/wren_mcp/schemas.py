"""MCP write-tool contract schemas (frozen).

Frozen MCP authoring contract, re-declared here because the MCP server ships as
a separate image with no backend-code dependency (the same "duplicated domain
truth kept in sync by contract" pattern as :mod:`wren_mcp.config`'s header
names). Inputs mirror the backend authoring types (ordered arrays + optional
``proposed_id``, key-addressed, never index-addressed). Outputs are **lean**
summary-first projections: a small ``patch`` returns ~50 tokens of changed-node
ids, and ``create``/``replace`` return identity + the ``proposed_id ->
minted_id`` remap rather than the whole document. ``visibility`` is web-only, so
it has no authoring input. Enforced by the schema snapshot and the cross-package
``contract-drift`` mirror test (``contract/tests/test_schema_mirror.py``).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


# ---------- Read/study switches ----------


class ResponseFormat(StrEnum):
    """The ``concise | detailed`` switch on the read tools.

    Concise (default) is roughly one-third the tokens and still carries every
    follow-up ID; detailed adds the explanatory free-text (a node ``description``
    on ``roadmap_get_node``, ``path_position`` on ``roadmap_get_next``)."""

    CONCISE = "concise"
    DETAILED = "detailed"


class SectionInclude(StrEnum):
    """Which parts of each node a ``roadmap_get_section`` page populates."""

    SUBSECTIONS = "subsections"
    ITEMS = "items"
    BOTH = "both"


class SearchHitKind(StrEnum):
    """Whether a search hit is a subsection (DAG node) or a checklist item."""

    SUBSECTION = "subsection"
    ITEM = "item"


class CompletionState(StrEnum):
    """The explicit target state ``progress_update`` sets its items to.

    Explicit set, never toggle: the client states the desired
    end state so a retry is idempotent."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


# A resource link constrained to an http(s) URL: rejects non-URLs (and empty
# strings) without normalizing the stored value. A plain ``str`` (not
# ``AnyUrl``) on purpose, mirroring the backend ``ResourceUrl`` so the frozen
# contract and the cross-package drift test stay in lockstep.
ResourceUrl = Annotated[str, Field(pattern=r"^https?://")]


# ---------- Authoring inputs (ordered arrays + optional proposed_id) ----------


class ResourceInput(BaseModel):
    """An external link on a subsection; the body is never inlined."""

    model_config = ConfigDict(extra="forbid")

    proposed_id: str | None = None
    title: str = Field(min_length=1)
    url: ResourceUrl
    type: ResourceType


class ChecklistItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_id: str | None = None
    text: str


class SubsectionInput(BaseModel):
    """A DAG node. Child collections are ordered arrays because IDs are
    server-minted; ``prereq_ids`` may reference sibling ``proposed_id``s."""

    model_config = ConfigDict(extra="forbid")

    proposed_id: str | None = None
    title: str = Field(min_length=1)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    effort_estimate: str | None = None
    prereq_ids: list[str] = Field(default_factory=list)
    resources: list[ResourceInput] = Field(default_factory=list)
    checklist_items: list[ChecklistItemInput] = Field(default_factory=list)


class SectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_id: str | None = None
    title: str = Field(min_length=1)
    subsections: list[SubsectionInput] = Field(default_factory=list)


class RoadmapDraftInput(BaseModel):
    """The full-document payload for ``create_roadmap_draft`` and
    ``replace_roadmap_draft``."""

    model_config = ConfigDict(extra="forbid")

    proposed_id: str | None = None
    title: str = Field(min_length=1)
    description: str | None = None
    subject_tags: list[str] = Field(default_factory=list)
    sections: list[SectionInput] = Field(default_factory=list)
    suggested_path: list[str] = Field(default_factory=list)


# ---------- Patch operation grammar (canonical dispatch) ----------------------
#
# One ``operations[]`` array applied atomically. Every op is key-addressed by
# slug ID; ordering uses ``before_id``/``after_id`` (never an array resend).
# ``add_*`` ops may carry an optional ``proposed_id``; the server mints one
# otherwise and echoes a ``proposed_id -> minted_id`` remap on de-dup.


class AddSubsectionOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_subsection"]
    section_id: str
    subsection: SubsectionInput
    before_id: str | None = None
    after_id: str | None = None


class UpdateSubsectionOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["update_subsection"]
    subsection_id: str
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    effort_estimate: str | None = None


class RemoveSubsectionOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_subsection"]
    subsection_id: str


class AddEdgeOp(BaseModel):
    """``to_id`` gains ``from_id`` as a prerequisite."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["add_edge"]
    from_id: str
    to_id: str


class RemoveEdgeOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_edge"]
    from_id: str
    to_id: str


class SetTagsOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["set_tags"]
    subsection_id: str
    tags: list[str] = Field(default_factory=list)


class SetResourcesOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["set_resources"]
    subsection_id: str
    resources: list[ResourceInput] = Field(default_factory=list)


class SetEffortOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["set_effort"]
    subsection_id: str
    effort_estimate: str | None = None


class AddItemOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_item"]
    subsection_id: str
    text: str
    proposed_id: str | None = None
    before_id: str | None = None
    after_id: str | None = None


class UpdateItemOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["update_item"]
    item_id: str
    text: str


class RemoveItemOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_item"]
    item_id: str


class ReorderOp(BaseModel):
    """Move any node (section / subsection / item) within its sibling order."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["reorder"]
    target_id: str
    before_id: str | None = None
    after_id: str | None = None


class SetSuggestedPathOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["set_suggested_path"]
    path: list[str] = Field(default_factory=list)


class AddSectionOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_section"]
    title: str = Field(min_length=1)
    proposed_id: str | None = None
    before_id: str | None = None
    after_id: str | None = None


class UpdateSectionOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["update_section"]
    section_id: str
    title: str = Field(min_length=1)


class RemoveSectionOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    without re-reading the whole roadmap (summary-first)."""

    kind: ChangedNodeKind
    id: str
    change: ChangeType


class Violation(BaseModel):
    """One structural rule failure, model-recoverable by naming the rule + IDs."""

    rule: str
    ids: list[str]
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


# ---------- Read projections (study-time) ------------------------------------
#
# These mirror the backend read projections (``wren.roadmaps.read_schemas`` /
# ``wren.progress.schemas``) field-for-field, so each read tool validates the
# backend body straight into the frozen MCP shape (``model_validate``) with no
# field renaming. Design rules encoded: summary-first (no item bodies on
# ``Overview``), resource links never inlined bodies, and the
# ``concise | detailed`` switch (the verbose ``description`` / ``path_position``
# is present only under detailed).


class ResourceRef(BaseModel):
    """A subsection resource as a link, never an inlined body."""

    id: str
    title: str
    url: str
    type: ResourceType


class PrereqRef(BaseModel):
    """A resolved prerequisite: its id, title, and the caller's done state
    (``done`` = every checklist item of the prerequisite subsection is checked)."""

    id: str
    title: str
    done: bool


class ItemState(BaseModel):
    """A checklist item with the caller's done state (``done`` = checked)."""

    id: str
    text: str
    done: bool


class NodeDetail(BaseModel):
    """One subsection resolved for study (``roadmap_get_node`` + section pages).

    ``description`` is populated only in ``detailed`` mode; concise leaves it
    ``None`` while still carrying every follow-up ID (subsection, resources,
    resolved prereqs, items). External bodies are never inlined: ``resources`` are
    links only."""

    subsection_id: str
    title: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    effort_estimate: str | None = None
    resources: list[ResourceRef] = Field(default_factory=list)
    prereqs: list[PrereqRef] = Field(default_factory=list)
    items: list[ItemState] = Field(default_factory=list)


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
    """``roadmap_get_overview`` result: the orientation call.

    Sections in ``section_order`` with per-section + overall completion and no
    checklist-item bodies; ``checked_items`` / ``percent`` reflect the caller's
    own progress. Drill in with ``roadmap_get_node`` or ``roadmap_get_section``."""

    roadmap_id: str
    title: str
    status: RoadmapStatus
    revision: int
    sections: list[SectionOverview] = Field(default_factory=list)
    overall: OverallProgress


class SectionPage(BaseModel):
    """``roadmap_get_section`` result: a paginated section drill-down.

    ``include`` selects which parts of each node are populated. ``next_cursor`` is
    an **opaque** token for the next page (absent on the last page); ``steering``
    is present only when the response was truncated ("showing N of M; pass
    cursor=..."). Pass ``next_cursor`` back as ``cursor`` to page forward."""

    section_id: str
    title: str
    include: SectionInclude
    subsections: list[NodeDetail] = Field(default_factory=list)
    next_cursor: str | None = None
    steering: str | None = None


class SearchHit(BaseModel):
    """One search match carrying the IDs needed to drill down.

    ``item_id`` is present only when ``kind == item``; ``matched_tags`` names the
    subsection tags that matched a tag filter (absent for a keyword-only match)."""

    kind: SearchHitKind
    subsection_id: str
    item_id: str | None = None
    title_or_text: str
    matched_tags: list[str] | None = None


class SearchResults(BaseModel):
    """``roadmap_search`` result: the matching hits (search, not list-all).

    A thin object wrapper around the hit list so the tool returns a structured
    ``outputSchema`` object like every other tool (rather than a bare array)."""

    hits: list[SearchHit] = Field(default_factory=list)


class ResourceLink(BaseModel):
    """A resource on a next item: a link, never an inlined body (no id needed)."""

    title: str
    url: str
    type: ResourceType


class NextItem(BaseModel):
    """One unchecked, prereq-satisfied checklist item to work on next.

    ``why_now`` is a STRUCTURAL rationale only: the mechanical
    facts the app owns (next unchecked in ``suggested_path``; named prerequisites
    complete), never pedagogical / ZPD judgement. ``path_position`` (the 1-based
    index of the item's subsection in ``suggested_path``) is present only in
    ``detailed`` mode."""

    subsection_id: str
    item_id: str
    text: str
    why_now: str
    resources: list[ResourceLink] = Field(default_factory=list)
    path_position: int | None = None


class NextResult(BaseModel):
    """``roadmap_get_next`` result: the next unchecked items in ``suggested_path``
    order whose prerequisites are all complete (server-computed).

    ``remaining_in_path`` counts the path subsections still to do; ``complete`` is
    ``True`` when nothing remains."""

    items: list[NextItem] = Field(default_factory=list)
    remaining_in_path: int = 0
    complete: bool = False


class SectionProgress(BaseModel):
    """Per-section completion counts, derived from progress + roadmap."""

    section_id: str
    total_items: int
    checked_items: int
    percent: int


class ProgressSnapshot(BaseModel):
    """``progress_get`` result: roadmap-wide + per-section completion.

    ``checked_ids`` is populated only under ``detailed`` (keeping the default
    concise and small while still letting the agent reconcile the exact checked
    set when it asks). ``deadline`` is the per-user countdown date, if set."""

    roadmap_id: str
    total_items: int
    checked_items: int
    percent: int
    deadline: date | None = None
    sections: list[SectionProgress] = Field(default_factory=list)
    checked_ids: list[str] | None = None


class ProgressUpdateResult(BaseModel):
    """``progress_update`` result: the fresh snapshot after the explicit set plus
    the next suggestion. The snapshot is detailed so the
    agent can reconcile its checkbox state to the server truth."""

    progress: ProgressSnapshot
    next: NextResult
