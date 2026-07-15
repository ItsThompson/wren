import type { components } from '@/api'

/**
 * Roadmap read types, sourced from the OpenAPI-generated client (never
 * hand-written; section 06/10 codegen contract). The `GET /roadmaps/{id}`
 * response is the full section-04 `Roadmap`.
 */
export type Roadmap = components['schemas']['Roadmap']
export type Section = components['schemas']['Section']
export type Subsection = components['schemas']['Subsection']
export type Resource = components['schemas']['Resource']
export type ChecklistItem = components['schemas']['ChecklistItem']
export type Violation = components['schemas']['Violation']
export type Visibility = components['schemas']['Visibility']

/**
 * Progress read types, also from the generated client. The published list view
 * fetches the detailed snapshot (for `checked_ids`) and posts explicit-set
 * updates (section 06/07).
 */
export type ProgressSnapshot = components['schemas']['ProgressSnapshot']
export type ProgressUpdateResult = components['schemas']['ProgressUpdateResult']

/**
 * The progress binding threaded from the list view down to each checklist row:
 * the derived done-state reads `checkedIds` and each toggle calls `onToggle`
 * (which persists via `progress_update`). Absent in draft preview mode, where
 * progress does not persist (section 10 "Preview mode").
 */
export interface ProgressBinding {
  checkedIds: Set<string>
  onToggle: (itemId: string, checked: boolean) => void
}

/**
 * A surfaced progress-write failure (section 10 "Any write"; ticket 26 / #9). A
 * failed persist is optimistically reverted and then announced instead of failing
 * silently: `stale` is a 409 re-read (US-ERR-01, shown as the ochre reload
 * prompt); `save-failed` is any other failure (shown as a quiet inline notice).
 */
export type ProgressNotice = { kind: 'stale' } | { kind: 'save-failed' }

/**
 * The roadmap-view fetch state as a single discriminated union so the impossible
 * "loaded with an error" combinations cannot arise (frontend state-structure
 * rule). `error.status` is the HTTP status (404/403 = unreachable) or null when
 * the request never resolved.
 */
export type RoadmapViewState =
  | { phase: 'loading' }
  | { phase: 'loaded'; roadmap: Roadmap }
  | { phase: 'error'; status: number | null }

/**
 * The publish action's sub-state, separate from the fetch state (a single
 * discriminated union so a success/blocked/failed combination cannot coexist).
 * `blocked` carries the structural violations returned by a 422 hard-block
 * (section 06) so the author sees the full fix list inline.
 */
export type PublishState =
  | { phase: 'idle' }
  | { phase: 'publishing' }
  | { phase: 'blocked'; violations: Violation[] }
  | { phase: 'failed'; status: number | null }

/**
 * The presentation-only fields editable via `PATCH /roadmaps/{id}/metadata`
 * (title / description / subject_tags), which stay mutable even after publish
 * (section 04/06). The metadata editor form collects exactly these.
 */
export interface MetadataDraft {
  title: string
  description: string
  subject_tags: string[]
}

/**
 * The metadata-edit sub-state. `saving` covers the in-flight PATCH; `failed`
 * carries the HTTP status (or null when the request never resolved) so the
 * editor can surface a retry message without conflating with the fetch state.
 */
export type MetadataEditState =
  | { phase: 'idle' }
  | { phase: 'saving' }
  | { phase: 'failed'; status: number | null }

/**
 * The fork sub-state. On success the view navigates to the new draft, so there
 * is no loaded-fork state here; `failed` carries the status for a retry message.
 */
export type ForkState = { phase: 'idle' } | { phase: 'forking' } | { phase: 'failed'; status: number | null }

/**
 * The web-only visibility toggle sub-state (`PUT /roadmaps/{id}/visibility`,
 * section 06). Last-write-wins: on success the returned roadmap replaces the
 * loaded one so the badge updates in place; `failed` carries the status.
 */
export type VisibilityState =
  | { phase: 'idle' }
  | { phase: 'saving' }
  | { phase: 'failed'; status: number | null }

/**
 * The web-only archive sub-state (`POST /roadmaps/{id}:archive`, section 06). On
 * success the returned archived roadmap replaces the loaded one; `failed` carries
 * the status for a retry message.
 */
export type ArchiveState =
  | { phase: 'idle' }
  | { phase: 'archiving' }
  | { phase: 'failed'; status: number | null }

/**
 * The web-only delete sub-state (`DELETE /roadmaps/{id}`, section 06). `blocked`
 * is the 409 `DELETE_HAS_FOLLOWERS` hard-stop: the roadmap has followers, so the
 * UI offers archive instead. A successful delete navigates away (no loaded
 * state); `failed` carries the status for a retry message.
 */
export type DeleteState =
  | { phase: 'idle' }
  | { phase: 'deleting' }
  | { phase: 'blocked' }
  | { phase: 'failed'; status: number | null }

/**
 * The owner-only web-only lifecycle bundle (visibility / archive / delete,
 * section 06). No agent surface: these are human-web actions only. Threaded into
 * the {@link RoadmapActions} bundle and rendered by `LifecycleActions` when the
 * signed-in user owns the roadmap.
 */
export interface RoadmapLifecycle {
  visibilityState: VisibilityState
  setVisibility: (visibility: Visibility) => void
  archiveState: ArchiveState
  archive: () => void
  deleteState: DeleteState
  deleteRoadmap: () => void
}

/**
 * The owner/reader action bundle threaded from RoadmapView into whichever view
 * renders (draft preview or published list). Fork is available to any reader;
 * the metadata edit and the web-only lifecycle actions are owner-only and gated
 * by `isOwner` at the render site.
 */
export interface RoadmapActions {
  metadataState: MetadataEditState
  editMetadata: (draft: MetadataDraft) => Promise<boolean>
  forkState: ForkState
  fork: () => void
  lifecycle: RoadmapLifecycle
}
