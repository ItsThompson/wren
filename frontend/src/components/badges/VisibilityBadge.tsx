import { Globe, Lock } from 'lucide-react'

import type { components } from '@/api'

type Visibility = components['schemas']['Visibility']

interface VisibilityBadgeProps {
  visibility: Visibility
}

/**
 * Visibility badge: a ghost pill with the lucide globe
 * (public) or lock (private) icon plus its text label, so visibility reads by
 * icon + word, never color alone.
 */
export function VisibilityBadge({ visibility }: VisibilityBadgeProps) {
  const isPublic = visibility === 'public'
  const Icon = isPublic ? Globe : Lock
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
      <Icon aria-hidden className="size-3" />
      {isPublic ? 'Public' : 'Private'}
    </span>
  )
}
