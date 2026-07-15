import { X } from 'lucide-react'
import type { ReactNode } from 'react'

interface InlineNoticeProps {
  /** The message; carried as text (never color alone). */
  children: ReactNode
  /** Dismiss handler; when present renders a quiet close control. */
  onDismiss?: () => void
}

/**
 * A quiet, non-intrusive inline notice for transient, self-recovered states,
 * such as a progress write that failed and was rolled back. Kept
 * neutral (ink on a muted surface, not ochre/brick) per the accent map: ochre is
 * reserved for the write-contract attention states, and informational emphasis
 * uses ink/neutral. `role="status"` announces it politely without stealing focus.
 */
export function InlineNotice({ children, onDismiss }: InlineNoticeProps) {
  return (
    <div
      role="status"
      className="flex items-start justify-between gap-3 rounded-md border border-border bg-muted px-4 py-3"
    >
      <p className="text-sm text-foreground">{children}</p>
      {onDismiss ? (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
        >
          <X aria-hidden className="size-4" />
        </button>
      ) : null}
    </div>
  )
}
