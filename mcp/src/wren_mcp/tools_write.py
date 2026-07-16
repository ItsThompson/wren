"""MCP write tools: the agent authoring surface.

Seven workflow-shaped write tools, registered on the shared FastMCP server
(:mod:`wren_mcp.mcp_server`) that :mod:`wren_mcp.app` mounts under the
bearer-guarded ``/mcp`` prefix. Each tool is a **thin adapter**: it resolves the
single ``user_id`` the request is scoped to (from the identity the bearer
boundary stashed on the request, never from a tool argument), makes one call to
the backend internal API via :class:`~wren_mcp.client.InternalApiClient`, and
maps the response to a lean, structured output. Backend failures surface as
model-recoverable :class:`ToolError`\\s (:mod:`wren_mcp.tool_errors`).

Annotations follow MCP guidance:
``readOnlyHint``/``idempotentHint``/``destructiveHint`` per tool. There is no
visibility, archive, or delete tool: those are web-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations

from wren_mcp.config import SCOPE_ROADMAPS_WRITE
from wren_mcp.schemas import (
    CreatedRoadmap,
    ForkResult,
    MetadataResult,
    PatchOp,
    PatchResult,
    PublishResult,
    ReplacedRoadmap,
    RoadmapDraftInput,
    ValidationResult,
)
from wren_mcp.scopes import AgentContext, require_scope
from wren_mcp.tool_errors import raise_for_problem
from wren_mcp.tool_registry import counted_tool_registrar

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from wren_mcp.client import InternalApiClient

_CREATE = ToolAnnotations(
    title="Create roadmap draft", readOnlyHint=False, destructiveHint=False, openWorldHint=False
)
_PATCH = ToolAnnotations(
    title="Patch roadmap draft",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_REPLACE = ToolAnnotations(
    title="Replace roadmap draft (import)",
    readOnlyHint=False,
    destructiveHint=True,
    openWorldHint=False,
)
_VALIDATE = ToolAnnotations(
    title="Validate roadmap draft",
    readOnlyHint=True,
    idempotentHint=True,
    openWorldHint=False,
)
_PUBLISH = ToolAnnotations(
    title="Publish roadmap", readOnlyHint=False, destructiveHint=True, openWorldHint=False
)
_FORK = ToolAnnotations(
    title="Fork roadmap", readOnlyHint=False, destructiveHint=False, openWorldHint=False
)
_EDIT_METADATA = ToolAnnotations(
    title="Edit roadmap metadata",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def register_write_tools(mcp: FastMCP, client: InternalApiClient) -> None:
    """Register the seven authoring tools onto ``mcp``, each closing over the
    injected internal client (the read tools are registered alongside).

    Each tool is registered through :func:`counted_tool_registrar`, so every call
    is counted as ``mcp_tool_invocations_total{tool,outcome}`` and the wrapper
    preserves the tool's name/signature so its exposed schema is unchanged.
    """

    tool = counted_tool_registrar(mcp)

    @tool(_CREATE)
    async def create_roadmap_draft(roadmap: RoadmapDraftInput, ctx: AgentContext) -> CreatedRoadmap:
        """Create a new roadmap draft from a full document. This is the one
        full-payload write (initial creation / import); use patch_roadmap_draft
        for every iterative edit. Supply a proposed_id on any node you plan to
        reference later: the server preserves it, or returns a
        proposed_id -> minted_id remap where it had to de-dupe, so you never
        address nodes by array position. Returns the minted roadmap_id. Read the
        authoring guidance (the shipped SKILL.md, served at GET /skill on the app)
        first: it explains ZPD sequencing, the suggested_path, and the structural
        validation contract you must satisfy to publish."""
        user_id = require_scope(ctx, scope=SCOPE_ROADMAPS_WRITE)
        response = await client.create_draft(user_id, roadmap.model_dump(mode="json"))
        return CreatedRoadmap.from_backend(raise_for_problem(response).json())

    @tool(_PATCH)
    async def patch_roadmap_draft(
        roadmap_id: str, revision: int, operations: list[PatchOp], ctx: AgentContext
    ) -> PatchResult:
        """Apply an ordered batch of typed, ID-addressed edits to a draft
        atomically (all-or-nothing). Pass the draft's current `revision` for
        optimistic concurrency: a stale revision fails with a re-read error
        (fetch the latest revision, then retry). Order edits with
        before_id/after_id, never by array position. The whole batch is validated
        together, INCLUDING that no intermediate step forms a prerequisite cycle,
        so order your add_edge ops to avoid a transient cycle even when the final
        graph is acyclic. add_* ops accept an optional proposed_id (echoed via
        remap on de-dup). Content edits are rejected on published/archived
        roadmaps (fork to change). Returns the new revision and changed nodes."""
        user_id = require_scope(ctx, scope=SCOPE_ROADMAPS_WRITE)
        payload = [op.model_dump(mode="json") for op in operations]
        response = await client.patch_draft(user_id, roadmap_id, revision, payload)
        return PatchResult.from_backend(raise_for_problem(response).json())

    @tool(_REPLACE)
    async def replace_roadmap_draft(
        roadmap_id: str, full_document: RoadmapDraftInput, ctx: AgentContext
    ) -> ReplacedRoadmap:
        """Replace a draft's entire document (import escape hatch only, never the
        iterative path; use patch_roadmap_draft to edit). The roadmap_id is
        unchanged; nodes carrying a proposed_id keep it, all others are re-minted
        (see remap). Reads the draft's current revision and imports under it
        (optimistic concurrency), so a concurrent edit surfaces a re-read error.
        Rejected on published/archived roadmaps."""
        user_id = require_scope(ctx, scope=SCOPE_ROADMAPS_WRITE)
        current = raise_for_problem(await client.get_roadmap(user_id, roadmap_id)).json()
        response = await client.replace_draft(
            user_id, roadmap_id, current["revision"], full_document.model_dump(mode="json")
        )
        return ReplacedRoadmap.from_backend(raise_for_problem(response).json())

    @tool(_VALIDATE)
    async def validate_roadmap_draft(roadmap_id: str, ctx: AgentContext) -> ValidationResult:
        """Return every structural violation for a draft in one pass without
        mutating it. publishable is true when there are no violations. Callable
        anytime on a draft."""
        user_id = require_scope(ctx, scope=SCOPE_ROADMAPS_WRITE)
        response = await client.validate_draft(user_id, roadmap_id)
        return ValidationResult.from_backend(raise_for_problem(response).json())

    @tool(_PUBLISH)
    async def publish_roadmap(roadmap_id: str, ctx: AgentContext) -> PublishResult:
        """Validate and transition a draft to published. This is one-way:
        published content is immutable (fork to change it). Refuses on any
        hard-block violation. Confirm with the user before publishing."""
        user_id = require_scope(ctx, scope=SCOPE_ROADMAPS_WRITE)
        response = await client.publish(user_id, roadmap_id)
        return PublishResult.from_backend(raise_for_problem(response).json())

    @tool(_FORK)
    async def fork_roadmap(source_roadmap_id: str, ctx: AgentContext) -> ForkResult:
        """Create a new draft seeded from any roadmap you can read, with fresh
        IDs and fresh progress. The source is untouched. Use this to change a
        published roadmap's structure."""
        user_id = require_scope(ctx, scope=SCOPE_ROADMAPS_WRITE)
        response = await client.fork(user_id, source_roadmap_id)
        return ForkResult.from_backend(
            raise_for_problem(response).json(), source_roadmap_id=source_roadmap_id
        )

    @tool(_EDIT_METADATA)
    async def edit_roadmap_metadata(
        roadmap_id: str,
        ctx: AgentContext,
        title: str | None = None,
        description: str | None = None,
        subject_tags: list[str] | None = None,
    ) -> MetadataResult:
        """Edit only presentation metadata (title, description, subject_tags);
        allowed on published roadmaps. Omitted fields are left unchanged. Never
        touches structure or revision; a structural change requires a draft
        (fork first)."""
        user_id = require_scope(ctx, scope=SCOPE_ROADMAPS_WRITE)
        response = await client.edit_metadata(
            user_id,
            roadmap_id,
            title=title,
            description=description,
            subject_tags=subject_tags,
        )
        return MetadataResult.from_backend(raise_for_problem(response).json())
