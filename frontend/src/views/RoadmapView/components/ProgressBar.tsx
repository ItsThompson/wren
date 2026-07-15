interface ProgressBarProps {
  checked: number
  total: number
  /** `roadmap` bars are 8px, `section` bars 6px (section 09 progress spec). */
  variant?: 'roadmap' | 'section'
  /** Accessible name for the bar (never color/number alone). */
  label: string
}

/**
 * A completion bar (section 09 "Progress"): full-pill `muted` track, solid
 * terracotta fill, percent in mono tabular numerals. Bars appear only at roadmap
 * and section level: subsections and items never get one (section 10).
 */
export function ProgressBar({ checked, total, variant = 'roadmap', label }: ProgressBarProps) {
  const percent = total === 0 ? 0 : Math.round((checked / total) * 100)
  const height = variant === 'roadmap' ? 'h-2' : 'h-1.5'

  return (
    <div className="flex items-center gap-3">
      <div
        role="progressbar"
        aria-label={label}
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        className={`${height} flex-1 overflow-hidden rounded-full bg-muted`}
      >
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-300"
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className="font-mono text-xs tabular-nums text-muted-foreground">{percent}%</span>
    </div>
  )
}
