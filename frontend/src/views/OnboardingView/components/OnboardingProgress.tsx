interface OnboardingProgressProps {
  /** 0-based index of the active step (from the hook's state). */
  stepIndex: number
  /** Total step count (from the ordered step list, via the hook's state). */
  stepCount: number
}

/**
 * The wizard's progress indicator. It reads the current index and total from the
 * hook's state (passed down by the orchestrator) rather than tracking position
 * itself, so the ordered step list stays the single source of order + count. A
 * row of dots gives the visual position; the `Step X of Y` label carries the
 * same meaning as text for assistive tech.
 */
export function OnboardingProgress({ stepIndex, stepCount }: OnboardingProgressProps) {
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: stepCount }, (_, index) => (
        <span
          key={index}
          aria-hidden
          className={`h-1.5 w-6 rounded-full ${
            index === stepIndex ? 'bg-primary' : 'bg-border'
          }`}
        />
      ))}
      <span className="sr-only">
        Step {stepIndex + 1} of {stepCount}
      </span>
    </div>
  )
}
