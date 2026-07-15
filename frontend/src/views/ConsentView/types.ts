/**
 * State shapes for the OAuth consent flow (SPA-rendered consent).
 *
 * The consent screen has two independent async concerns: loading the parked
 * request's context (client name + requested scopes, keyed by the opaque
 * `auth_request_id`) and submitting the human's decision. Each is modeled as a
 * discriminated union so impossible combinations (e.g. "loaded but errored")
 * cannot arise (frontend state-structure rule).
 */

export type ConsentContextState =
  | { phase: 'loading' }
  | { phase: 'error' }
  | { phase: 'loaded'; clientName: string; scopes: string[] }

export type DecisionState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'error'; message: string }
