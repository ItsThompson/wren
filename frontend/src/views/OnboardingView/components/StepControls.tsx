import { Button } from '@/components/ui/button'

/** Shown on the control that completes onboarding while its request is in flight. */
const PENDING_LABEL = 'Finishing\u2026'

interface StepControlsProps {
  /** `actions.next`, or `actions.submit` on the last step. */
  onContinue: () => void
  /** `actions.back` (control hidden on the first step). */
  onBack: () => void
  /** `actions.skip` (shares the completion path with the final-step primary). */
  onSkip: () => void
  isFirstStep: boolean
  isLastStep: boolean
  isSubmitting: boolean
  /** Inline completion-failure message to surface, or `null`. */
  error: string | null
  /** Primary action label, e.g. "Continue" or "Get started". */
  continueLabel: string
}

/**
 * The shared step footer: the primary action, an optional Back (absent on the
 * first step, so Welcome has no Back), and Skip, plus an inline completion-error
 * alert. Skip and the final-step primary share one completion path, so whichever
 * one completes on this step (Skip on non-final steps, the primary on the final
 * step) shows the pending label while the request is in flight; every control is
 * disabled meanwhile to prevent a double-submit.
 */
export function StepControls({
  onContinue,
  onBack,
  onSkip,
  isFirstStep,
  isLastStep,
  isSubmitting,
  error,
  continueLabel,
}: StepControlsProps) {
  return (
    <>
      {error ? (
        <p role="alert" className="mt-6 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="mt-8 flex flex-col gap-2">
        <Button onClick={onContinue} disabled={isSubmitting}>
          {isSubmitting && isLastStep ? PENDING_LABEL : continueLabel}
        </Button>
        {isFirstStep ? null : (
          <Button variant="ghost" onClick={onBack} disabled={isSubmitting}>
            Back
          </Button>
        )}
        <Button variant="ghost" onClick={onSkip} disabled={isSubmitting}>
          {isSubmitting && !isLastStep ? PENDING_LABEL : 'Skip'}
        </Button>
      </div>
    </>
  )
}
