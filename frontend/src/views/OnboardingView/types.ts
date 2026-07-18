/**
 * Types for the onboarding wizard. The wizard is a state-machine hook + thin
 * presentational steps + a thin orchestrator (frontend feature-dir pattern).
 * In this epic steps collect no input; the reusable "few skippable steps ending
 * in a terminal completion" shape is preserved so data-collecting steps can be
 * added later without reshaping the hook.
 */

/**
 * Identifies a step. This is a const map + derived union rather than a TS
 * `enum`: the app tsconfig sets `erasableSyntaxOnly`, which forbids enums (see
 * `views/TreeView/types.ts` for the same pattern). Order is defined by the
 * ordered `STEPS` list (steps.ts), not by this map.
 */
export const OnboardingStepId = {
  WELCOME: 'welcome',
  CONNECT_AGENT: 'connect_agent',
  HOW_IT_WORKS: 'how_it_works',
} as const

export type OnboardingStepId = (typeof OnboardingStepId)[keyof typeof OnboardingStepId]

/**
 * A step's static definition. Steps are presentational in this epic and the
 * ordered list (steps.ts) is the single source of step order + count, so a step
 * carries only its id; the orchestrator routes on `id` and renders each concrete
 * step with its own props.
 */
export interface OnboardingStep {
  id: OnboardingStepId
}

/**
 * The wizard's observable state. A single object (with `phase`/`error` derived
 * from one internal union) so impossible combinations, e.g. submitting with an
 * error still set, are not representable.
 */
export interface OnboardingState {
  /** 0-based index into the ordered step list. */
  stepIndex: number
  /** Total steps, for the progress indicator. */
  stepCount: number
  /** `stepIndex === 0` (Welcome): no Back. */
  isFirstStep: boolean
  /** On the last step the primary action completes instead of advancing. */
  isLastStep: boolean
  /** Completion-call state. */
  phase: 'idle' | 'submitting' | 'error'
  /** User-facing message when `phase === 'error'`, else `null`. */
  error: string | null
}

/** Actions the hook exposes. `skip` and `submit` share the same terminal path. */
export interface OnboardingActions {
  /** Advance one step (no-op on the last step). */
  next: () => void
  /** Go back one step (no-op on the first step). */
  back: () => void
  /** End onboarding now: complete → apply user → navigate. */
  skip: () => void
  /** Final-step completion: complete → apply user → navigate. */
  submit: () => void
}

/**
 * The shared navigation contract every step receives. Steps emit intent only;
 * they never call the network or read auth/env directly.
 */
export interface OnboardingStepProps {
  /** `actions.next`, or `actions.submit` on the last step. */
  onContinue: () => void
  /** `actions.back`. */
  onBack: () => void
  /** `actions.skip`. */
  onSkip: () => void
  isFirstStep: boolean
  isLastStep: boolean
  /** Disable controls / show pending while the completion call is in flight. */
  isSubmitting: boolean
  /** Inline completion-failure message to surface on the step, or `null`. */
  error: string | null
}

/**
 * ConnectAgentStep additionally receives its display config as props. These are
 * sourced once at the view root (`mcpUrl` from `VITE_MCP_BASE_URL`; the hrefs as
 * constants) and threaded down, so the step stays presentational and never reads
 * `import.meta.env` or hardcodes routes itself.
 */
export interface ConnectAgentStepProps extends OnboardingStepProps {
  /** The Wren MCP server URL to add to an MCP client (from `VITE_MCP_BASE_URL`). */
  mcpUrl: string
  /** Route to the Connected agents surface. */
  connectionsHref: string
  /** Absolute URL of the docs Getting Started guide. */
  docsHref: string
}
