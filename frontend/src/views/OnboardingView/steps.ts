import { OnboardingStepId, type OnboardingStep } from './types'

/**
 * The ordered wizard steps: the single source of step order + count. Both the
 * progress indicator and the hook's `stepCount`/`isFirstStep`/`isLastStep`
 * bounds derive from this list, never from a counter tracked inside a step.
 *
 * This slice ships only the Welcome step (the walking skeleton that drives the
 * complete/skip terminal path end to end). Later steps are appended here.
 */
export const STEPS: readonly OnboardingStep[] = [{ id: OnboardingStepId.WELCOME }]
