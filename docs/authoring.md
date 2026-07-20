# Authoring roadmaps

How draft content is written, and why published content cannot be. Content authoring goes through one `RoadmapService` (`backend/src/wren/roadmaps/`), so the rules below hold identically wherever the write comes from.

A roadmap is authored as a **draft**, then **published** in a one-way transition that freezes its structure. There are two ways to write draft content and a hard boundary that stops either from touching published content.

## Where content authoring happens

Content authoring (create, patch, replace, validate) has **no web UI**. It is agent-only, driven by an AI agent through the MCP tools. The web SPA surfaces no content-editing form.

The backend authoring endpoints exist on both apps and enforce the same rules; the SPA simply does not call the content-write ones. The sanctioned web edits are the presentation-only metadata edit and the lifecycle actions (publish, fork, visibility, archive, delete). See `api.md` for which endpoints mount where.

For the study-time read surface and the follow model (following is created implicitly by the first progress write, not by an explicit follow button), see `progress.md`.

## Two write paths: patch vs replace

| Path | Endpoint / tool | When |
|------|-----------------|------|
| Iterative edit | `PATCH /roadmaps/{id}` / `patch_roadmap_draft` | **The primary path.** Typed, ID-addressed, atomic operations. A small edit costs a few tokens instead of resending the whole document. |
| Full-document import | `PUT /roadmaps/{id}` / `replace_roadmap_draft` | **A documented escape hatch only, never the iterative path.** Replaces the entire draft in one shot: use it to import a document authored elsewhere, not to make an incremental change. |

Both are draft-only content writes, both are guarded by `If-Match: <revision>` optimistic concurrency (a stale revision is a `409 STALE_REVISION` telling the caller to re-read), and both bump `revision` on success. Prefer `patch` for everyday editing; reach for `replace` only when you genuinely have a whole new document to import.

### Replace: ID semantics

`replace` accepts the same `RoadmapInput` full-document shape as `create`. When it rebuilds the draft:

- The roadmap's own ID (the route param) is **unchanged**.
- Any node that carries a `proposed_id` **keeps it** (validated, slugified, and de-duped like `create`).
- Every node **without** a `proposed_id` is **re-minted** from its title.
- `owner` and `created_at` are preserved, `visibility` is taken from the stored draft (never the imported document), and `revision` is bumped.

The response is the full rebuilt roadmap plus a `remap` of any `proposed_id -> minted_id` that changed (de-dup **or** normalization), so the caller can reconcile its references.

The input shapes and the shared mint-then-resolve rebuild module live in `backend/src/wren/roadmaps/`.

## The immutability boundary

Publishing is where followers start tracking progress against a roadmap's structure, so **published (and archived) content is immutable**. Every structural write path is refused on a non-draft roadmap:

- `create` produces a fresh draft, `patch` and `replace` both load through the service's content-write guard, and all of them reject a `published`/`archived` roadmap with a `409 IMMUTABLE` problem+json.
- The error points to **fork-to-change**: forking produces a new draft under a brand-new roadmap ID (child slug IDs are copied verbatim, since their uniqueness scope is a single roadmap) with no progress carry-over, which can then be edited and published on its own.

Fork (`POST /roadmaps/{id}:fork` / the fork MCP tool) works from any roadmap the caller can **read**: their own (any status) or a public one. A private roadmap owned by someone else is a 404, leaking no existence. The fork is owned by the forking user and starts private at `revision` 1.

The only sanctioned write on published content is a **presentation-only** metadata edit (`title`, `description`, `subject_tags`) via `PATCH /roadmaps/{id}/metadata` (or the edit-metadata MCP tool). That path does not go through the content-write guard, which is exactly why it stays allowed after publish while structural writes do not. It is deliberately **not** `If-Match`-guarded and never bumps the structural `revision` (last-write-wins presentation edits at the ~5-user scale); a smuggled structural/lifecycle field (e.g. `sections`, `visibility`) is rejected with a `409 IMMUTABLE` rather than silently applied.

| Field group | Post-publish |
|-------------|--------------|
| Structure and content (sections, subsections, items, prereq edges, `suggested_path`, resources, effort, track tags) | Immutable: fork to change |
| Presentation (`title`, `description`, `subject_tags`) | Editable by the owner |
| Lifecycle (`visibility`, archive/delete) | Web-only |
