import { useState } from 'react'
import { Archive, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { RoadmapLifecycle, Roadmap } from '../types'
import { PublishedVisibilityControl } from './PublishedVisibilityControl'

interface LifecycleActionsProps {
  roadmap: Roadmap
  lifecycle: RoadmapLifecycle
  isMutationPending: boolean
}

/**
 * The owner-only web-only lifecycle bar (destructive = brick fill,
 * confirm-gated): a publication-access toggle plus the
 * confirm-gated archive and delete actions. No agent surface exists for any of
 * these; they are human-web only.
 *
 * PublishedVisibility is a reversible ghost toggle (lock/globe) so it is not confirm-gated.
 * Archive and delete are destructive (brick `destructive` Button) and require an
 * inline confirm step before firing. Archive is offered only on a published
 * roadmap (the linear draft -> published -> archived lifecycle). Delete is guarded
 * server-side by a zero-followers check: a `blocked` result (409) steers the owner
 * to archive instead.
 */
export function LifecycleActions({ roadmap, lifecycle, isMutationPending }: LifecycleActionsProps) {
  const [confirming, setConfirming] = useState<'archive' | 'delete' | null>(null)
  const { publishedVisibilityState, setPublishedVisibility, archiveState, archive, deleteState, deleteRoadmap } =
    lifecycle

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
      <PublishedVisibilityControl
        status={roadmap.status}
        publishedVisibility={roadmap.published_visibility}
        saving={publishedVisibilityState.phase === 'saving'}
        disabled={isMutationPending}
        onChange={setPublishedVisibility}
      />

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {canArchive ? (
          <Button
            type="button"
            variant="destructive"
            onClick={() => setConfirming('archive')}
            disabled={isMutationPending || confirming !== null}
          >
            <Archive aria-hidden />
            {isArchiving ? 'Archiving…' : 'Archive'}
          </Button>
        ) : null}
        <Button
          type="button"
          variant="destructive"
          onClick={() => setConfirming('delete')}
          disabled={isMutationPending || confirming !== null}
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
            <Button type="button" variant="destructive" onClick={confirmAction} disabled={isMutationPending}>
              {confirming === 'delete' ? 'Confirm delete' : 'Confirm archive'}
            </Button>
            <Button type="button" variant="outline" onClick={() => setConfirming(null)} disabled={isMutationPending}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}

      {deleteState.phase === 'blocked' ? (
        <p className="mt-3 text-sm text-muted-foreground" role="alert">
          {roadmap.status === 'published'
            ? 'This roadmap has followers, so it can’t be deleted. Archive it instead to retire it while existing followers keep their progress.'
            : 'This roadmap has followers, so it can’t be deleted. Existing followers keep their progress.'}
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

      {publishedVisibilityState.phase === 'failed' ? (
        <p className="mt-3 text-sm text-muted-foreground" role="alert">
          We couldn&rsquo;t update publication access. Please try again.
        </p>
      ) : null}
    </section>
  )
}
