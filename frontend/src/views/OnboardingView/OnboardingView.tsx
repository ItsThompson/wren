import type { ReactNode } from 'react'

import { OnboardingProgress } from './components/OnboardingProgress'
import { WelcomeStep } from './components/WelcomeStep'
import { useOnboarding } from './hooks/useOnboarding'
import { STEPS } from './steps'
import { OnboardingStepId, type OnboardingStepProps } from './types'

/**
 * OnboardingView: the thin orchestrator. It composes the state-machine hook with
 * the progress indicator and the active step, and renders a chrome-free
 * full-viewport frame (it lives outside `AppShell`, so there is no TopBar or page
 * gutter). All state and the completion call live in {@link useOnboarding}; steps
 * receive callbacks + flags and emit intent only.
 *
 * The active step routes on the step's `id` (a switch, so each concrete step can
 * receive its own props). In this slice only Welcome exists and it is also the
 * last step, so its primary action maps to the completion path (`submit`);
 * `next` is wired for the multi-step content added later.
 */
export function OnboardingView() {
  const { state, actions } = useOnboarding()
  const step = STEPS[state.stepIndex]

  const stepProps: OnboardingStepProps = {
    onContinue: state.isLastStep ? actions.submit : actions.next,
    onBack: actions.back,
    onSkip: actions.skip,
    isFirstStep: state.isFirstStep,
    isLastStep: state.isLastStep,
    isSubmitting: state.phase === 'submitting',
    error: state.error,
  }

  let activeStep: ReactNode
  switch (step.id) {
    case OnboardingStepId.WELCOME:
      activeStep = <WelcomeStep {...stepProps} />
      break
  }

  return (
    <main className="flex min-h-screen flex-col bg-background px-5 py-10">
      <div className="mx-auto flex w-full max-w-[32rem] flex-1 flex-col justify-center">
        <OnboardingProgress stepIndex={state.stepIndex} stepCount={state.stepCount} />
        <div className="mt-10">{activeStep}</div>
      </div>
    </main>
  )
}
