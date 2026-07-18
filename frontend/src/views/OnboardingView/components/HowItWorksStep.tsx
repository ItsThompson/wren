import type { OnboardingStepProps } from '../types'
import { StepControls } from './StepControls'

/**
 * The How-it-works step: the final step. Presentational, mirroring the docs
 * Getting Started guide (agents author roadmaps; humans follow and track them)
 * and its draft \u2192 publish \u2192 follow \u2192 track lifecycle. Being last, its primary
 * action completes onboarding, so the orchestrator maps Continue to the
 * completion path and the control reads "Get started".
 */
export function HowItWorksStep({
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
      <p className="text-sm font-medium text-muted-foreground">How Wren works</p>
      <h1 className="display-l mt-3 text-foreground">Agents author, you follow</h1>
      <p className="mt-4 max-w-[52ch] text-muted-foreground">
        A connected agent drafts a roadmap and publishes it when it&rsquo;s ready. You follow a
        published roadmap to start learning, and Wren tracks your progress and suggests what to do
        next: so agents author and keep roadmaps current while you follow and track them.
      </p>

      <StepControls
        onContinue={onContinue}
        onBack={onBack}
        onSkip={onSkip}
        isFirstStep={isFirstStep}
        isLastStep={isLastStep}
        isSubmitting={isSubmitting}
        error={error}
        continueLabel="Get started"
      />
    </div>
  )
}
