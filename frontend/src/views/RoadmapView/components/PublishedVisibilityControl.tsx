import { Globe, Lock } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { PublishedVisibility, RoadmapStatus } from '../types'

interface PublishedVisibilityControlProps {
  status: RoadmapStatus
  publishedVisibility: PublishedVisibility
  saving: boolean
  disabled: boolean
  onChange: (publishedVisibility: PublishedVisibility) => void
}

export function PublishedVisibilityControl({
  status,
  publishedVisibility,
  saving,
  disabled,
  onChange,
}: PublishedVisibilityControlProps) {
  const isPublic = publishedVisibility === 'public'
  const label = status === 'draft' ? 'Public when published' : isPublic ? 'Public access' : 'Private access'
  const helper = status === 'draft'
    ? 'Drafts remain private until you publish this roadmap.'
    : status === 'archived'
      ? isPublic
        ? 'Anyone with the link can read this roadmap. It is hidden from discovery.'
        : 'Only you can read this roadmap. It is hidden from discovery.'
      : isPublic
        ? 'Anyone with the link can read this roadmap.'
        : 'Only you can read this roadmap.'
  const Icon = isPublic ? Globe : Lock

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        type="button"
        variant="ghost"
        aria-pressed={isPublic}
        onClick={() => onChange(isPublic ? 'private' : 'public')}
        disabled={disabled || saving}
      >
        <Icon aria-hidden />
        {saving ? 'Saving…' : label}
      </Button>
      <span className="text-sm text-muted-foreground">{helper}</span>
    </div>
  )
}
