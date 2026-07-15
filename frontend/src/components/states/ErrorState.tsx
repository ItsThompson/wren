import type { ReactNode } from 'react'

interface ErrorStateProps {
  /** The failure headline (e.g. "Roadmap not found"). */
  title: string
  /** A muted sub-line explaining the failure; optional. */
  description?: string
  /** A recovery affordance (retry button / link back); optional. */
  action?: ReactNode
}

/**
 * A full-view error surface (spec section 10 error states): a headline, a muted
 * explanation, and an optional recovery action. Text-first and `role="alert"` so
 * meaning never rides on color alone (§9 accessibility). Used for dedicated
 * 404/403 views (which share one message so a private roadmap's existence never
 * leaks) and for generic load failures with a retry. Shared across views so
 * error surfaces read consistently.
 */
export function ErrorState({ title, description, action }: ErrorStateProps) {
  return (
    <section className="reading-width py-16 text-center" role="alert">
      <h1 className="display-m text-foreground">{title}</h1>
      {description ? (
        <p className="mx-auto mt-4 max-w-[42ch] text-muted-foreground">{description}</p>
      ) : null}
      {action ? <div className="mt-6 flex justify-center">{action}</div> : null}
    </section>
  )
}
