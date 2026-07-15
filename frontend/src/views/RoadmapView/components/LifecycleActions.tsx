import { useState } from 'react'
import { Archive, Globe, Lock, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { RoadmapLifecycle, Roadmap } from '../types'

interface LifecycleActionsProps {
  roadmap: Roadmap
  lifecycle: RoadmapLifecycle
}

/**
 * The owner-only web-only lifecycle bar (destructive = brick fill,
 * confirm-gated): a visibility toggle plus the
 * confirm-gated archive and delete actions. No agent surface exists for any of
 * these; they are human-web only.
 *
 * Visibility is a reversible ghost toggle (lock/globe) so it is not confirm-gated.
 * Archive and delete are destructive (brick `destructive` Button) and require an
 * inline confirm step before firing. Archive is offered only on a published
 * roadmap (the linear draft -> published -> archived lifecycle). Delete is guarded
 * server-side by a zero-followers check: a `blocked` result (409) steers the owner
 * to archive instead.
 */
export function LifecycleActions({ roadmap, lifecycle }: LifecycleActionsProps) {
  const [confirming, setConfirming] = useState<'archive' | 'delete' | null>(null)
  const { visibilityState, setVisibility, archiveState, archive, deleteState, deleteRoadmap } =
    lifecycle

  const isPublic = roadmap.visibility === 'public'
  const isSavingVisibility = visibilityState.phase === 'saving'
  const isArchiving = archiveState.phase === 'archiving'
  const isDeleting = deleteState.phase === 'deleting'
  const canArchive = roadmap.status === 'published'

  const confirmAction = () => {
    if (confirming === 'archive') archive()
    if (confirming === 'delete') deleteRoadmap()
    setConfirming(null)
  }

  return (
    <section className="mt-6 border-t border-border pt-6" aria-label="Roadmap lifecycle">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="ghost"
          onClick={() => setVisibility(isPublic ? 'private' : 'public')}
          disabled={isSavingVisibility}
        >
          {isPublic ? <Globe aria-hidden /> : <Lock aria-hidden />}
          {isPublic ? 'Make private' : 'Make public'}
        </Button>
        <span className="text-sm text-muted-foreground">
          {isPublic ? 'Public: anyone with the link can find this.' : 'Private: only you can see this.'}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {canArchive ? (
          <Button
            type="button"
            variant="destructive"
            onClick={() => setConfirming('archive')}
            disabled={isArchiving || confirming !== null}
          >
            <Archive aria-hidden />
            {isArchiving ? 'Archiving…' : 'Archive'}
          </Button>
        ) : null}
        <Button
          type="button"
          variant="destructive"
          onClick={() => setConfirming('delete')}
          disabled={isDeleting || confirming !== null}
        >
          <Trash2 aria-hidden />
          {isDeleting ? 'Deleting…' : 'Delete'}
        </Button>
      </div>

      {confirming !== null ? (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/5 p-4" role="alertdialog" aria-label={`Confirm ${confirming}`}>
          <p className="text-sm text-foreground">
            {confirming === 'delete'
              ? 'Delete this roadmap permanently? This cannot be undone.'
              : 'Archive this roadmap? It will be hidden from discovery, but existing followers keep it and their progress.'}
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            <Button type="button" variant="destructive" onClick={confirmAction}>
              {confirming === 'delete' ? 'Confirm delete' : 'Confirm archive'}
            </Button>
            <Button type="button" variant="outline" onClick={() => setConfirming(null)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}

      {deleteState.phase === 'blocked' ? (
        <p className="mt-3 text-sm text-muted-foreground" role="alert">
          This roadmap has followers, so it can&rsquo;t be deleted. Archive it instead to retire it
          while existing followers keep their progress.
        </p>
      ) : null}

      {deleteState.phase === 'failed' ? (
        <p className="mt-3 text-sm text-muted-foreground" role="alert">
          We couldn&rsquo;t delete this roadmap. Please try again.
        </p>
      ) : null}

      {archiveState.phase === 'failed' ? (
        <p className="mt-3 text-sm text-muted-foreground" role="alert">
          We couldn&rsquo;t archive this roadmap. Please try again.
        </p>
      ) : null}

      {visibilityState.phase === 'failed' ? (
        <p className="mt-3 text-sm text-muted-foreground" role="alert">
          We couldn&rsquo;t update visibility. Please try again.
        </p>
      ) : null}
    </section>
  )
}
