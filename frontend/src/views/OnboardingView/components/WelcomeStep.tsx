import type { OnboardingStepProps } from '../types'
import { StepControls } from './StepControls'

/**
 * The Welcome step: a chrome-free intro to Wren. It is presentational: it emits
 * navigation intent through the props the orchestrator wires and never touches
 * the network or auth state. The Back/Continue/Skip controls and the inline
 * completion-error alert live in {@link StepControls}; Welcome is the first step,
 * so Back is absent and Continue advances to the next step.
 */
export function WelcomeStep({
  onContinue,
  onBack,
  onSkip,
  isFirstStep,
  isLastStep,
  isSubmitting,
  error,
}: OnboardingStepProps) {
  return (
    <div className="flex flex-col">
      <p className="text-sm font-medium text-muted-foreground">Welcome to Wren</p>
      <h1 className="display-l mt-3 text-foreground">Let&rsquo;s get you set up</h1>
      <p className="mt-4 max-w-[52ch] text-muted-foreground">
        Wren turns any subject into a prerequisite-ordered roadmap you can follow and track, with
        agents that author and update it for you.
      </p>

      <StepControls
        onContinue={onContinue}
        onBack={onBack}
        onSkip={onSkip}
        isFirstStep={isFirstStep}
        isLastStep={isLastStep}
        isSubmitting={isSubmitting}
        error={error}
        continueLabel="Continue"
      />
    </div>
  )
}
