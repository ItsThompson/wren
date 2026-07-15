import type { components } from '@/api'

/** A roadmap summarized for a card (the generated list projection). */
export type RoadmapCardData = components['schemas']['RoadmapCard']

/**
 * The dashboard fetch state as a single discriminated union so the impossible
 * "loaded with an error" combinations cannot arise (frontend state-structure
 * rule). Gated on an authenticated session by the caller.
 */
export type DashboardState =
  | { phase: 'loading' }
  | { phase: 'error' }
  | { phase: 'loaded'; authored: RoadmapCardData[]; followed: RoadmapCardData[] }
