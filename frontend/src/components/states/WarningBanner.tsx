import { TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'

interface WarningBannerProps {
  /** The headline of the warning; carried as text, never color alone. */
  title: string
  /** Supporting copy / a list of details. */
  children?: ReactNode
  /** An optional recovery affordance (reload / fork). */
  action?: ReactNode
}

/**
 * The shared ochre (warning) surface for the first-class attention states of the
 * write contract: stale-revision re-read, the immutable
 * fork-to-change prompt, and publish hard-block violations. Meaning is carried by
 * the lucide alert icon AND the heading text, with ochre only as reinforcement,
 * so it is never encoded by color alone (§9/§10 accessibility). `role="alert"`
 * announces it to assistive tech. Compose it via the specific notices rather than
 * using it directly.
 */
export function WarningBanner({ title, children, action }: WarningBannerProps) {
  return (
    <div role="alert" className="rounded-lg border border-warning/50 bg-warning/10 p-4">
      <div className="flex items-start gap-3">
        <TriangleAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-warning" />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-foreground">{title}</p>
          {children ? (
            <div className="mt-1 text-sm text-muted-foreground">{children}</div>
          ) : null}
          {action ? <div className="mt-3">{action}</div> : null}
        </div>
      </div>
    </div>
  )
}
