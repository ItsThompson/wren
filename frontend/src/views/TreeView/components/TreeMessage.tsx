import type { ReactNode } from 'react'

interface TreeMessageProps {
  title: string
  description: string
  action?: ReactNode
}

/**
 * A centered empty/error message for the tree view, following the design
 * language empty-state pattern (Fraunces line + muted sub-line + one action).
 * Ticket 26 harmonizes empty/error states across the app; this is the basic
 * in-view state until then.
 */
export function TreeMessage({ title, description, action }: TreeMessageProps) {
  return (
    <div className="mx-auto flex max-w-[520px] flex-col items-center gap-3 py-24 text-center">
      <h2 className="display-m text-foreground">{title}</h2>
      <p className="text-muted-foreground">{description}</p>
      {action}
    </div>
  )
}
