import { OnboardingStepId, type OnboardingStep } from './types'

/**
 * The ordered wizard steps: the single source of step order + count. Both the
 * progress indicator and the hook's `stepCount`/`isFirstStep`/`isLastStep`
 * bounds derive from this list, never from a counter tracked inside a step.
 *
 * The narrative is Welcome → ConnectAgent → HowItWorks (mirroring the docs
 * Getting Started guide). Reordering or adding steps here is the only change
 * needed to reshape the wizard's flow and progress.
 */
export const STEPS: readonly OnboardingStep[] = [
  { id: OnboardingStepId.WELCOME },
  { id: OnboardingStepId.CONNECT_AGENT },
  { id: OnboardingStepId.HOW_IT_WORKS },
]
