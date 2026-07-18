import { Button } from '@/components/ui/button'

import type { OnboardingStepProps } from '../types'

/**
 * The Welcome step: a chrome-free intro to Wren with a primary action and a
 * Skip. It is presentational: it emits navigation intent through the props the
 * orchestrator wires (`onContinue`/`onSkip`) and never touches the network or
 * auth state. In this walking-skeleton slice Welcome is also the last step, so
 * the orchestrator maps `onContinue` to the completion path; `isSubmitting`
 * disables both controls against a double-submit, and `error` surfaces an inline
 * completion failure for retry.
 */
export function WelcomeStep({ onContinue, onSkip, isSubmitting, error }: OnboardingStepProps) {
  return (
    <div className="flex flex-col">
      <p className="text-sm font-medium text-muted-foreground">Welcome to Wren</p>
      <h1 className="display-l mt-3 text-foreground">Let&rsquo;s get you set up</h1>
      <p className="mt-4 max-w-[52ch] text-muted-foreground">
        Wren turns any subject into a prerequisite-ordered roadmap you can follow and track, with
        agents that author and update it for you.
      </p>

      {error ? (
        <p role="alert" className="mt-6 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="mt-8 flex flex-col gap-2">
        <Button onClick={onContinue} disabled={isSubmitting}>
          {isSubmitting ? 'Finishing\u2026' : 'Continue'}
        </Button>
        <Button variant="ghost" onClick={onSkip} disabled={isSubmitting}>
          Skip
        </Button>
      </div>
    </div>
  )
}
