---
name: wren
description: Use Wren's MCP tools to create, edit, publish, and study personalized learning roadmaps and track progress. Load for any Wren roadmap or learning-progress request. Covers learner goals, ZPD sequencing, Bloom-level assessment, resources, and tool workflows.
---

# Wren

Wren is a store for personalized **learning roadmaps**. You (the user's agent) are connected to it over MCP. This guide covers both authoring and studying a roadmap. Sequence learning by the learner's **Zone of Proximal Development (ZPD)**: each step is challenging but reachable given what they already know.

## The app is a tool, not the decision-maker

Wren does five key things: it **stores** roadmaps, **validates their structure**, **renders** them, **tracks progress**, and **hosts these tools**.

Everything that makes a roadmap good is your job, done before you write anything:

- **Model the learner.** Ask what they already know, what level of understanding they want to achieve, and how much time they have. Do not assume a blank slate or a mastery goal.
- **Discover prerequisites.** Decide which concepts must precede which.
- **Gather resources.** Find a concrete article/video/course/doc for each node.
- **Sequence by ZPD.** Order the work so each step builds on the last.

Wren never computes ZPD, never reasons about pedagogy, and never reorders your work. The `suggested_path` you author **is** your sequencing intent, frozen at publish time. If the roadmap is not well-sequenced, that is on you, not the tool.

## Set the learning target with Bloom's taxonomy

Ask the learner what level of understanding they want to achieve before designing a roadmap. Use plain language rather than asking them to pick a taxonomy label: "Do you want to recognize and explain the ideas, use them in practice, compare and judge approaches, or build something new?" If their goal already answers this, confirm the target rather than asking again. If it remains unclear, ask instead of assuming.

Use the revised Bloom's taxonomy as a guide to the kind of work the learner should be able to do: **remember, understand, apply, analyze, evaluate, create**. These are types of learning outcomes, not a requirement to put every subsection through all six levels. A learner who wants to apply a topic may need to remember and explain its basics first; a learner seeking an overview does not need projects that demand evaluation or creation.

Match the roadmap's depth, resources, and checklist items to the chosen target. Write observable outcomes (for example, "explain why X works" or "apply X to solve Y") rather than vague items such as "understand X". Include lower-level prerequisites where needed, but stop when the learner can demonstrate the requested level. Use ZPD to decide the order of reachable steps; use the target level to decide how far those steps go.

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

- **Prerequisite edges** between subsections form a **DAG** (directed, acyclic). An edge means "learn X before Y".
- **`suggested_path`** is an ordered list of every subsection ID. It expresses your ZPD sequencing and must be a valid topological order of the DAG.

### Address everything by ID, never by array index

Every node has a **server-minted slug ID** (e.g. `sub_python-basics`). All edits target these IDs. There is no array-index addressing anywhere: you never say "the third subsection". When you create or import content, attach a `proposed_id` to any node you intend to reference later; the server preserves it (or returns a `proposed_id -> minted_id` remap if it had to de-dupe), so you always have a stable handle. Ordering is expressed with `before_id` / `after_id`, never by resending an array.

Slug IDs are stable and diverge from titles: renaming a subsection does **not** change its ID. Keep addressing by ID.

## The tools

### Authoring and publication

| Tool | Use it for |
|------|-----------|
| `create_roadmap_draft(roadmap)` | **Initial authoring / import.** The one legitimate full-document write. Returns the `roadmap_id`, `revision`, and any `proposed_id -> minted_id` remap |
| `patch_roadmap_draft(roadmap_id, revision, operations)` | **Every iterative edit.** Typed, ID-addressed, atomic operations. A small change costs a few tokens instead of resending the whole document |
| `replace_roadmap_draft(roadmap_id, full_document)` | **Import escape hatch only, never the iterative path.** Replaces the entire draft in one shot; use it only to re-import a document authored elsewhere |
| `validate_roadmap_draft(roadmap_id)` | Return every structural violation in one pass without mutating. Callable anytime |
| `publish_roadmap(roadmap_id)` | Validate + transition draft → published. **One-way.** Confirm with the user first |
| `fork_roadmap(source_roadmap_id)` | New draft seeded from any roadmap you can read, with fresh IDs and progress. The only way to change published structure |
| `edit_roadmap_metadata(roadmap_id, ...)` | Presentation-only edit (`title`, `description`, `subject_tags`); allowed even on published roadmaps |

**`patch` is the primary path; `replace` is not.** Reach for `replace` only when you genuinely have a whole new document to import. For everyday editing (rename a subsection, add a resource, insert an item, add a prerequisite edge, reorder), use `patch`.

### Study and progress

| Tool | Use it for |
|------|-----------|
| `roadmap_list()` | Find your authored and followed roadmaps when the ID is unknown |
| `roadmap_get_profile(handle)` | Find published public roadmaps from a profile handle |
| `roadmap_get(roadmap_id)` | Retrieve the full roadmap when inspection or export needs every detail |
| `roadmap_get_overview(roadmap_id, format?)` | See sections and completion counts; detailed format includes the suggested path |
| `roadmap_get_next(roadmap_id, format?)` | Find unchecked items whose prerequisites are complete, in suggested-path order |
| `roadmap_get_node(roadmap_id, subsection_id, format?)` | Study one subsection with its resources, prerequisites, and checklist items |
| `roadmap_get_section(roadmap_id, section_id, cursor?, include?)` | Browse a section in pages; pass back the returned cursor to continue |
| `roadmap_search(roadmap_id, query, tags?)` | Search subsections and checklist items by keyword or track tag |
| `progress_get(roadmap_id, detailed?)` | See completion totals; detailed mode also returns completed item IDs |
| `progress_update(roadmap_id, item_ids, state)` | Set items complete or incomplete; returns updated progress and the next suggestion |

## Authoring workflow

1. **Ask for the learner's target level** and current knowledge, then design the roadmap off-app: sections, subsections and prerequisite edges, checklist items at the appropriate Bloom level, a resource per subsection, and the ZPD `suggested_path`.
2. **`create_roadmap_draft`** with the full first draft. Put a `proposed_id` on every subsection you will reference in edges or in `suggested_path`.
3. **Iterate with `patch_roadmap_draft`.** Pass the current `revision`; batch related edits into one atomic call. Order operations so the graph stays valid at every step (see the transient-cycle rule below).
4. **`validate_roadmap_draft`** and fix every violation. Validation returns the complete list at once, each naming the offending IDs.
5. **Confirm with the user**, then **`publish_roadmap`**.

### Ordering operations and the transient-cycle rule

Edges are added with `add_edge(from_id, to_id)`: this records that `from_id` is a prerequisite of `to_id` (learn `from_id` first).

A `patch` batch is applied **atomically** (all-or-nothing), and every operation that adds a prerequisite edge (`add_edge`, or an `add_subsection` carrying `prereq_ids`) is checked for acyclicity **after each edge-affecting operation**, not just at the end of the batch. So a batch that would create a cycle *midway* is rejected even when the final graph would be acyclic.

**Order your `add_edge` operations so the DAG stays acyclic at each step.** Add edges in dependency order (prerequisites first) and never introduce an edge whose reverse you plan to remove later in the same batch. The error names the cycle so you can reorder and retry.

### Optimistic concurrency

Content writes carry the draft's `revision`. If it is stale (someone else edited in between) the tool returns a re-read error: fetch the current state, rebase your change, and retry with the fresh `revision`. Never guess a revision number.

## The structural validation contract (V1-V8)

`publish` hard-blocks on any of these; `validate` reports all of them at once. Author to satisfy them from the start:

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

V3 and V4 together are why `suggested_path` is load-bearing: it is both the complete list of nodes and their learning order. Keep it in sync as you add or remove subsections (`set_suggested_path` in a patch).

## Publishing is one-way: confirm first

Publishing freezes the roadmap's structure so followers can track progress against it. **Published (and archived) content is immutable.** After publish you can only edit presentation metadata (`title`, `description`, `subject_tags`); to change structure you must `fork_roadmap` into a new draft and publish that.

Because it cannot be undone:

1. **Share a preview** with the user (walk them through the sections and the suggested path; the study-time read tools help you narrate it).
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
        checklist_items: [{ text: "Explain how contiguous storage supports indexed access" }] },
      { proposed_id: "sub_hashing", title: "Hashing",
        prereq_ids: ["sub_arrays"],
        resources: [{ title: "Hash functions", url: "https://...", type: "video" }],
        checklist_items: [{ text: "Explain a hash function" }] }
    ]
  }],
  suggested_path: ["sub_arrays", "sub_hashing"]
})
```

Then iterate. For example, extend the roadmap with a new subsection, wire its prerequisite, and keep `suggested_path` in sync, in one atomic patch:

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

The `add_edge` names `sub_hashing` before `sub_collisions`, so the DAG stays acyclic as the batch applies. Validate, confirm with the user, then publish.

## Studying a roadmap

Start with the roadmap overview and next eligible items, then open the chosen subsection. The suggested path is the default order; prerequisites are the hard constraint. Follow the learner's preference when prerequisites allow it.

Study one subsection at a time:

1. Read the primary source yourself before teaching so explanations match its facts and notation. Use a PDF-to-text skill for PDFs. If the source is unavailable, say so rather than inventing its contents.
2. Assign the subsection's resources with focus points that name what the learner should extract. Let the learner study the resources before you explain or assess.
3. Assess each checklist item at the level its outcome requires within the learner's chosen goal: recall a fact, explain an idea in their own words, apply it to a new case, analyze a comparison, evaluate a choice with reasons, or create an artifact. Recall alone does not demonstrate application, analysis, evaluation, or creation. Allow notes and tools when the real task calls for them, but require independent work rather than a verbatim copy of the tutor's answer.
4. Mark an item complete only after the learner demonstrates its outcome. Set its progress explicitly with `progress_update`. If the learner misses it, teach the specific gap and reassess later with a fresh prompt; mark it complete once they succeed.
