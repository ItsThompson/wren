import { useState } from 'react'

import { Button } from '@/components/ui/button'
import type { MetadataDraft, RoadmapActions as Actions, Roadmap } from '../types'
import { LifecycleActions } from './LifecycleActions'
import { MetadataEditor } from './MetadataEditor'

interface RoadmapActionsProps {
  roadmap: Roadmap
  /** Whether the signed-in user owns this roadmap (owner-only metadata edit). */
  isOwner: boolean
  actions: Actions
}

/**
 * The owner/reader action bar for a roadmap (section 05 fork + metadata edit).
 *
 * Fork is offered to any reader (you can fork a public roadmap or your own),
 * producing a fresh draft the view then navigates to. The presentation-only
 * "Edit details" affordance is owner-only and opens the {@link MetadataEditor}
 * inline; it stays available even on a published roadmap because editing
 * title/description/subject_tags is the sanctioned post-publish edit. The
 * owner-only web-only lifecycle bar ({@link LifecycleActions}: visibility toggle
 * + confirm-gated archive/delete) renders below, for the roadmap's owner.
 */
export function RoadmapActions({ roadmap, isOwner, actions }: RoadmapActionsProps) {
  const [editing, setEditing] = useState(false)
  const isForking = actions.forkState.phase === 'forking'

  const handleSave = async (draft: MetadataDraft) => {
    const saved = await actions.editMetadata(draft)
    if (saved) setEditing(false)
  }

  return (
    <section className="mt-6 border-t border-border pt-6">
      <div className="flex flex-wrap items-center gap-3">
        {isOwner ? (
          <Button
            type="button"
            variant="outline"
            onClick={() => setEditing((open) => !open)}
            aria-expanded={editing}
          >
            {editing ? 'Close editor' : 'Edit details'}
          </Button>
        ) : null}
        <Button type="button" variant="secondary" onClick={actions.fork} disabled={isForking}>
          {isForking ? 'Forking…' : 'Fork'}
        </Button>
        <p className="text-sm text-muted-foreground">
          Fork to make your own editable copy as a new draft.
        </p>
      </div>

      {isOwner && editing ? (
        <div className="mt-4">
          <MetadataEditor
            roadmap={roadmap}
            state={actions.metadataState}
            onSave={handleSave}
            onCancel={() => setEditing(false)}
          />
        </div>
      ) : null}

      {actions.forkState.phase === 'failed' ? (
        <p className="mt-3 text-sm text-muted-foreground" role="alert">
          We couldn&rsquo;t fork this roadmap. Please try again.
        </p>
      ) : null}

      {isOwner ? <LifecycleActions roadmap={roadmap} lifecycle={actions.lifecycle} /> : null}
    </section>
  )
}
