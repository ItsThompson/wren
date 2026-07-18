import type { HowItWorksStepData } from '../types'

interface HowItWorksStepProps {
  step: HowItWorksStepData
  index: number
}

/**
 * One numbered "How it works" step: a lucide icon, a two-digit step number, a
 * grotesque title, and a one-line explanation. Presentational.
 */
export function HowItWorksStep({ step, index }: HowItWorksStepProps) {
  const { icon: Icon, title, body } = step
  return (
    <li className="rounded-2xl border border-border bg-card p-6">
      <div className="flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-full bg-accent text-accent-foreground">
          <Icon aria-hidden className="size-5" />
        </span>
        <span className="font-mono text-sm tabular-nums text-muted-foreground">
          {String(index + 1).padStart(2, '0')}
        </span>
      </div>
      <h3 className="mt-4 text-lg font-semibold text-foreground">{title}</h3>
      <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{body}</p>
    </li>
  )
}
