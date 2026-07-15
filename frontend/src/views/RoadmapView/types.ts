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
