import type { components } from '@/api'

/** One authorized agent, sourced from the OpenAPI-generated client. */
export type ConnectedClient = components['schemas']['ConnectedClient']

/**
 * The connected-clients list fetch as a single discriminated union so the
 * impossible "loaded with an error" combinations cannot arise (frontend
 * state-structure rule).
 */
export type ClientsListState =
  | { phase: 'loading' }
  | { phase: 'error' }
  | { phase: 'loaded'; clients: ConnectedClient[] }
