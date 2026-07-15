import type { components } from '@/api'

/** The public profile body (the generated list projection). */
export type ProfileData = components['schemas']['Profile']

/**
 * The profile fetch state as a single discriminated union. `notfound` is the
 * 404 for an unknown handle (its own first-class UI state, section 10); `error`
 * covers any other failure with an inline retry.
 */
export type ProfileState =
  | { phase: 'loading' }
  | { phase: 'notfound' }
  | { phase: 'error' }
  | { phase: 'loaded'; profile: ProfileData }
