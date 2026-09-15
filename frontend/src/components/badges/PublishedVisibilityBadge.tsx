import { Globe, Lock } from 'lucide-react'

import type { components } from '@/api'

type PublishedVisibility = components['schemas']['PublishedVisibility']
type RoadmapStatus = components['schemas']['RoadmapStatus']

interface PublishedVisibilityBadgeProps {
  publishedVisibility: PublishedVisibility
  status: RoadmapStatus
}

/**
 * Shows whether a roadmap is public or private. Drafts describe the future
 * publication state so the badge never implies that a draft is link-readable.
 */
export function PublishedVisibilityBadge({ publishedVisibility, status }: PublishedVisibilityBadgeProps) {
  const isPublic = publishedVisibility === 'public'
  const Icon = isPublic ? Globe : Lock
  const label = status === 'draft'
    ? isPublic ? 'Public when published' : 'Private when published'
    : isPublic ? 'Public' : 'Private'
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
      <Icon aria-hidden className="size-3" />
      {label}
    </span>
  )
}
