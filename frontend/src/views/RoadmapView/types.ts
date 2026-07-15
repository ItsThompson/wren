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
