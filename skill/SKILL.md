---
name: wren-roadmap-authoring
description: >
  Author genuinely ZPD-ordered, well-structured learning roadmaps in Wren via
  the connected MCP tools. Activate whenever a user asks you to create, edit, or
  publish a learning roadmap on Wren. You own the teaching: modelling what the
  learner already knows, discovering prerequisites, gathering resources, and
  sequencing by Zone of Proximal Development. Wren stores, validates structure,
  renders, and tracks progress: it does not do the pedagogy.
---

# Authoring roadmaps in Wren

Wren is a store for personalized **learning roadmaps**. You (the user's agent)
are connected to it over MCP. This guide steers you to produce a roadmap that is
genuinely sequenced by the learner's **Zone of Proximal Development (ZPD)**: each
step is challenging but reachable given what they already know.

## The load-bearing idea: you are the brain, not the app

Wren does five things and no more: it **stores** roadmaps, **validates their
structure**, **renders** them, **tracks progress**, and **hosts these tools**.
Everything that makes a roadmap good is your job, done before you write anything:

- **Model the learner.** Ask (or infer from context) what they already know, what
  they're aiming at, and how much time they have. Do not assume a blank slate.
- **Discover prerequisites.** Decide which concepts must precede which.
- **Gather resources.** Find a concrete article/video/course/doc for each node.
- **Sequence by ZPD.** Order the work so each step builds on the last.

Wren never computes ZPD, never reasons about pedagogy, and never reorders your
work. The `suggested_path` you author **is** your sequencing intent, frozen at
publish time. If the roadmap is not well-sequenced, that is on you, not the tool.
Keep roadmaps light and iterate with the user: a first draft is a starting point,
not a final artifact.

## The model

A roadmap is a small tree with one graph inside it:

| Level | What it is | Notes |
|-------|-----------|-------|
| **Roadmap** | The whole artifact | Has a title, optional description, optional subject tags |
| **Section** | An ordered phase | Organizational grouping only. Must hold ≥ 1 subsection |
| **Subsection** | A **DAG node** | The unit of the prerequisite graph. Carries tags, resources, effort, and prerequisite edges |
| **Checklist item** | The only checkable unit | Progress is tracked here. Each subsection needs ≥ 1 |
| **Resource** | A link on a subsection | `{title, url, type}`. Never inlined content, always a link. Each subsection needs ≥ 1 |

Two cross-cutting structures:

- **Prerequisite edges** between subsections form a **DAG** (directed, acyclic).
  An edge means "learn X before Y".
- **`suggested_path`** is an ordered list of every subsection ID. It expresses
  your ZPD sequencing and must be a valid topological order of the DAG.

### Address everything by ID, never by array index

Every node has a **server-minted slug ID** (e.g. `sub_python-basics`). All edits
target these IDs. There is no array-index addressing anywhere: you never say
"the third subsection". When you create or import content, attach a `proposed_id`
to any node you intend to reference later; the server preserves it (or returns a
`proposed_id -> minted_id` remap if it had to de-dupe), so you always have a
stable handle. Ordering is expressed with `before_id` / `after_id`, never by
resending an array.

Slug IDs are stable and diverge from titles: renaming a subsection does **not**
change its ID. Keep addressing by ID.

## The tools

| Tool | Use it for |
|------|-----------|
| `create_roadmap_draft(roadmap)` | **Initial authoring / import.** The one legitimate full-document write. Returns the `roadmap_id`, `revision`, and any `proposed_id -> minted_id` remap |
| `patch_roadmap_draft(roadmap_id, revision, operations)` | **Every iterative edit.** Typed, ID-addressed, atomic operations. A small change costs a few tokens instead of resending the whole document |
| `replace_roadmap_draft(roadmap_id, full_document)` | **Import escape hatch only, never the iterative path.** Replaces the entire draft in one shot; use it only to re-import a document authored elsewhere |
| `validate_roadmap_draft(roadmap_id)` | Return every structural violation in one pass without mutating. Callable anytime |
| `publish_roadmap(roadmap_id)` | Validate + transition draft → published. **One-way.** Confirm with the user first |
| `fork_roadmap(source_roadmap_id)` | New draft seeded from any roadmap you can read, with fresh IDs and progress. The only way to change published structure |
| `edit_roadmap_metadata(roadmap_id, ...)` | Presentation-only edit (`title`, `description`, `subject_tags`); allowed even on published roadmaps |

**`patch` is the primary path; `replace` is not.** Reach for `replace` only when
you genuinely have a whole new document to import. For everyday editing (rename a
subsection, add a resource, insert an item, add a prerequisite edge, reorder),
use `patch`.

## Authoring workflow

1. **Model the learner** and design the roadmap off-app: the sections, the
   subsections and their prerequisite edges, the checklist items, a resource per
   subsection, and the ZPD `suggested_path`.
2. **`create_roadmap_draft`** with the full first draft. Put a `proposed_id` on
   every subsection you will reference in edges or in `suggested_path`.
3. **Iterate with `patch_roadmap_draft`.** Pass the current `revision`; batch
   related edits into one atomic call. Order operations so the graph stays valid
   at every step (see the transient-cycle rule below).
4. **`validate_roadmap_draft`** and fix every violation. Validation returns the
   complete list at once, each naming the offending IDs.
5. **Confirm with the user**, then **`publish_roadmap`**.

### Ordering operations and the transient-cycle rule

Edges are added with `add_edge(from_id, to_id)`: this records that `from_id` is a
prerequisite of `to_id` (learn `from_id` first).

A `patch` batch is applied **atomically** (all-or-nothing), and every operation
that adds a prerequisite edge (`add_edge`, or an `add_subsection` carrying
`prereq_ids`) is checked for acyclicity **after each edge-affecting operation**,
not just at the end of the batch. So a batch that would create a cycle *midway*
is rejected even when the final graph would be acyclic.
**Order your `add_edge` operations so the DAG stays acyclic at each step.** Add
edges in dependency order (prerequisites first) and never introduce an edge whose
reverse you plan to remove later in the same batch. The error names the cycle so
you can reorder and retry.

### Optimistic concurrency

Content writes carry the draft's `revision`. If it is stale (someone else edited
in between) the tool returns a re-read error: fetch the current state, rebase your
change, and retry with the fresh `revision`. Never guess a revision number.

## The structural validation contract (V1–V8)

`publish` hard-blocks on any of these; `validate` reports all of them at once.
Author to satisfy them from the start:

| Rule | Requirement |
|------|-------------|
| **V1** | The prerequisite DAG is **acyclic** (no cycle of `prereq_ids`) |
| **V2** | **No dangling prerequisites**: every `prereq_id` references an existing subsection |
| **V3** | `suggested_path` **covers every subsection exactly once** (none missing, none duplicated, none unknown) |
| **V4** | `suggested_path` is a **valid topological order**: no prerequisite appears after a subsection that depends on it |
| **V5** | Every **section has ≥ 1 subsection** |
| **V6** | Every **subsection has ≥ 1 checklist item** |
| **V7** | Every **subsection has ≥ 1 resource** |
| **V8** | **Non-empty titles** on the roadmap and every section, subsection, and checklist item |

V3 and V4 together are why `suggested_path` is load-bearing: it is both the
complete list of nodes and their learning order. Keep it in sync as you add or
remove subsections (`set_suggested_path` in a patch).

## Publishing is one-way: confirm first

Publishing freezes the roadmap's structure so followers can track progress
against it. **Published (and archived) content is immutable.** After publish you
can only edit presentation metadata (`title`, `description`, `subject_tags`); to
change structure you must `fork_roadmap` into a new draft and publish that.

Because it cannot be undone:

1. **Share a preview** with the user (walk them through the sections and the
   suggested path; the study-time read tools help you narrate it).
2. **Gather feedback** and apply it with `patch`.
3. **Get explicit confirmation** that they want to publish.
4. Only then call **`publish_roadmap`**.

Do not publish on your own initiative.

## Worked example (shape only)

```
create_roadmap_draft({
  title: "Intro to Hash Tables",
  subject_tags: ["data-structures"],
  sections: [{
    proposed_id: "sec_foundations",
    title: "Foundations",
    subsections: [
      { proposed_id: "sub_arrays", title: "Arrays",
        resources: [{ title: "Arrays 101", url: "https://...", type: "article" }],
        checklist_items: [{ text: "Understand contiguous storage" }] },
      { proposed_id: "sub_hashing", title: "Hashing",
        prereq_ids: ["sub_arrays"],
        resources: [{ title: "Hash functions", url: "https://...", type: "video" }],
        checklist_items: [{ text: "Explain a hash function" }] }
    ]
  }],
  suggested_path: ["sub_arrays", "sub_hashing"]
})
```

Then iterate. For example, extend the roadmap with a new subsection, wire its
prerequisite, and keep `suggested_path` in sync, in one atomic patch:

```
patch_roadmap_draft(roadmap_id, revision, [
  { op: "add_subsection", section_id: "sec_foundations", after_id: "sub_hashing",
    subsection: { proposed_id: "sub_collisions", title: "Collision handling",
      resources: [{ title: "Open addressing", url: "https://...", type: "article" }],
      checklist_items: [{ text: "Compare chaining vs open addressing" }] } },
  { op: "add_edge", from_id: "sub_hashing", to_id: "sub_collisions" },
  { op: "set_suggested_path", path: ["sub_arrays", "sub_hashing", "sub_collisions"] }
])
```

The `add_edge` names `sub_hashing` before `sub_collisions`, so the DAG stays
acyclic as the batch applies. Validate, confirm with the user, then publish.
