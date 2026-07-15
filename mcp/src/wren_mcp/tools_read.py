"""MCP read tools: the agent study-time surface.

The six workflow-shaped read tools plus ``progress_update``, registered on the
shared FastMCP server (:mod:`wren_mcp.mcp_server`) that :mod:`wren_mcp.app` mounts
under the bearer-guarded ``/mcp`` prefix, alongside the write tools.
Each tool is a **thin adapter**: it enforces the required OAuth scope and resolves
the single ``user_id`` the request is scoped to (:func:`require_scope`, never a
tool argument), makes **one** call to a backend internal read route via
:class:`~wren_mcp.client.InternalApiClient`, and validates the response into the
frozen read projection. Backend failures surface as model-recoverable
:class:`ToolError`\\s (:mod:`wren_mcp.tool_errors`).

Design rules: summary-first then drill-down; the
``concise | detailed`` switch; resource links never inlined bodies; the one
many-item tool (``roadmap_get_section``) paginates via an opaque cursor and
carries steering text on truncation. Annotations: the six reads are
``readOnlyHint``; ``progress_update`` is an explicit-set write, so it is
``idempotentHint`` (a retry is a no-op), ``destructiveHint: false``, not readOnly.

``roadmap_get_next`` maps to the server-side ``next.compute``: the
agent never receives the full checked set or every ``prereq_ids`` (a context
blow-up), only the next prereq-satisfied items with a STRUCTURAL ``why_now``.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from wren_mcp.client import InternalApiClient
from wren_mcp.config import SCOPE_PROGRESS_WRITE, SCOPE_ROADMAPS_READ
from wren_mcp.schemas import (
    CompletionState,
    NextResult,
    NodeDetail,
    Overview,
    ProgressSnapshot,
    ProgressUpdateResult,
    ResponseFormat,
    SearchResults,
    SectionInclude,
    SectionPage,
)
from wren_mcp.scopes import AgentContext, require_scope
from wren_mcp.tool_errors import raise_for_problem
from wren_mcp.tool_registry import counted_tool_registrar

_OVERVIEW = ToolAnnotations(title="Get roadmap overview", readOnlyHint=True, openWorldHint=False)
_NEXT = ToolAnnotations(title="Get next steps", readOnlyHint=True, openWorldHint=False)
_NODE = ToolAnnotations(title="Get subsection detail", readOnlyHint=True, openWorldHint=False)
_SECTION = ToolAnnotations(title="Get section page", readOnlyHint=True, openWorldHint=False)
_SEARCH = ToolAnnotations(title="Search roadmap", readOnlyHint=True, openWorldHint=False)
_PROGRESS_GET = ToolAnnotations(title="Get progress", readOnlyHint=True, openWorldHint=False)
_PROGRESS_UPDATE = ToolAnnotations(
    title="Update progress",
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def register_read_tools(mcp: FastMCP, client: InternalApiClient) -> None:
    """Register the seven study-time tools onto ``mcp``, each closing over the
    injected internal client (Ticket 21 registers the write tools alongside)."""

    tool = counted_tool_registrar(mcp)

    @tool(_OVERVIEW)
    async def roadmap_get_overview(
        roadmap_id: str, ctx: AgentContext, format: ResponseFormat = ResponseFormat.CONCISE
    ) -> Overview:
        """Orientation call: the sections in order with per-section and overall
        completion counts/percent for your progress, and no checklist-item bodies.
        Start here, then drill into a node (roadmap_get_node) or a section
        (roadmap_get_section). Use format=detailed for the fuller projection."""
        user_id = require_scope(ctx, scope=SCOPE_ROADMAPS_READ)
        response = await client.get_overview(user_id, roadmap_id, format.value)
        return Overview.model_validate(raise_for_problem(response).json())

    @tool(_NEXT)
    async def roadmap_get_next(
        roadmap_id: str, ctx: AgentContext, format: ResponseFormat = ResponseFormat.CONCISE
    ) -> NextResult:
        """The next unchecked items to work on: those in the author's suggested
        path whose prerequisites you have all completed, in path order. Each item
        carries a structural why_now (its path position + that its named
        prerequisites are done) and resource links; remaining_in_path counts the
        path subsections still to do, and complete is true when nothing remains.
        format=detailed adds each item's path_position. The pedagogical judgement
        is the author's (baked into the path); this only reports structure."""
        user_id = require_scope(ctx, scope=SCOPE_ROADMAPS_READ)
        response = await client.get_next(user_id, roadmap_id, format.value)
        return NextResult.model_validate(raise_for_problem(response).json())

    @tool(_NODE)
    async def roadmap_get_node(
        roadmap_id: str,
        subsection_id: str,
        ctx: AgentContext,
        format: ResponseFormat = ResponseFormat.CONCISE,
    ) -> NodeDetail:
        """One subsection resolved for study: its tags, effort estimate, resource
        links (never inlined bodies), prerequisites resolved to {id, title, done},
        and checklist items as {id, text, done} for your progress. An unknown
        subsection_id returns an error naming the valid sibling ids. Concise omits
        the long description; pass format=detailed to include it."""
        user_id = require_scope(ctx, scope=SCOPE_ROADMAPS_READ)
        response = await client.get_node(user_id, roadmap_id, subsection_id, format.value)
        return NodeDetail.model_validate(raise_for_problem(response).json())

    @tool(_SECTION)
    async def roadmap_get_section(
        roadmap_id: str,
        section_id: str,
        ctx: AgentContext,
        cursor: str | None = None,
        include: SectionInclude = SectionInclude.BOTH,
    ) -> SectionPage:
        """Paginated drill-down into one section's subsections (server-set page
        size). include selects what each node carries: subsections (metadata),
        items (checklist only), or both. On a truncated page, next_cursor is an
        opaque token and steering says how many remain: pass next_cursor back as
        cursor to fetch the next page. Omit cursor for the first page."""
        user_id = require_scope(ctx, scope=SCOPE_ROADMAPS_READ)
        response = await client.get_section(user_id, roadmap_id, section_id, cursor, include.value)
        return SectionPage.model_validate(raise_for_problem(response).json())

    @tool(_SEARCH)
    async def roadmap_search(
        roadmap_id: str, query: str, ctx: AgentContext, tags: list[str] | None = None
    ) -> SearchResults:
        """Find subsections and checklist items by keyword and/or track tag (a
        search, not a list-all). Each hit carries the ids needed to drill in
        (subsection_id, and item_id for an item hit). Pass tags to filter to
        subsections carrying any of those track tags."""
        user_id = require_scope(ctx, scope=SCOPE_ROADMAPS_READ)
        response = await client.search(user_id, roadmap_id, query, tags)
        body = raise_for_problem(response).json()
        return SearchResults(hits=body)

    @tool(_PROGRESS_GET)
    async def progress_get(
        roadmap_id: str, ctx: AgentContext, detailed: bool = False
    ) -> ProgressSnapshot:
        """Your progress against the roadmap: overall and per-section counts and
        percent, plus your deadline if set. Concise by default; pass detailed=true
        to also get checked_ids (the exact set of completed checklist-item ids)."""
        user_id = require_scope(ctx, scope=SCOPE_ROADMAPS_READ)
        response = await client.get_progress(user_id, roadmap_id, detailed)
        return ProgressSnapshot.model_validate(raise_for_problem(response).json())

    @tool(_PROGRESS_UPDATE)
    async def progress_update(
        roadmap_id: str, item_ids: list[str], state: CompletionState, ctx: AgentContext
    ) -> ProgressUpdateResult:
        """Set the given checklist items to a state (complete or incomplete) in one
        batch. This is an explicit set, not a toggle, so a retry is idempotent. An
        unknown item id (not part of this roadmap) is rejected and nothing is
        applied. Returns the fresh progress snapshot plus the next suggestion, so
        you can continue the study loop without a second read."""
        user_id = require_scope(ctx, scope=SCOPE_PROGRESS_WRITE)
        response = await client.update_progress(user_id, roadmap_id, item_ids, state.value)
        return ProgressUpdateResult.model_validate(raise_for_problem(response).json())
