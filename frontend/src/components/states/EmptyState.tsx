import type { ReactNode } from 'react'

interface EmptyStateProps {
  /** The Fraunces display line: warm, encouraging, second person (§7.8). */
  title: string
  /** A muted sub-line elaborating the state; optional. */
  description?: string
  /** At most one primary action (a `<Button>` / link); optional. */
  action?: ReactNode
}

/**
 * The design-language empty-state pattern (spec section 09 §7.8): one Fraunces
 * `display-m` line, a muted sub-line, and at most one primary action. The single
 * place Fraunces + warmth shine in a dense app; keep the copy encouraging. Shared
 * across every view so empty states read consistently (ticket 26).
 */
export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="py-14 text-center">
      <p className="display-m text-foreground">{title}</p>
      {description ? (
        <p className="mx-auto mt-3 max-w-[44ch] text-muted-foreground">{description}</p>
      ) : null}
      {action ? <div className="mt-6 flex justify-center">{action}</div> : null}
    </div>
  )
}
