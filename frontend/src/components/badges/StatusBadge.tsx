import type { components } from '@/api'
import { cn } from '@/lib/utils'

type RoadmapStatus = components['schemas']['RoadmapStatus']

/**
 * Lifecycle-status badge: Draft is a neutral muted pill,
 * Published an olive tint, Archived a muted outline. The text label always
 * carries the meaning, so status is never encoded by color alone (accessibility).
 */
const STATUS_STYLES: Record<RoadmapStatus, { label: string; className: string }> = {
  draft: { label: 'Draft', className: 'bg-muted text-muted-foreground' },
  published: { label: 'Published', className: 'bg-success/15 text-success' },
  archived: {
    label: 'Archived',
    className: 'border border-muted-foreground/40 text-muted-foreground',
  },
}

interface StatusBadgeProps {
  status: RoadmapStatus
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const { label, className } = STATUS_STYLES[status]
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium',
        className,
      )}
    >
      {label}
    </span>
  )
}
