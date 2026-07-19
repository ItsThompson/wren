import { useCallback, useMemo, useState } from 'react'

import { keys, runQuery, useApiQuery, useSessionClient } from '@/api'
import { isStaleRevision, toProblem } from '@/lib/problem'
import { firstNextSubsectionId, patchCheckedIds, patchDeadline } from '../util/progress-derive'
import type { ProgressNotice } from '../types'

/**
 * Fetch and mutate the caller's progress for one published roadmap. Both reads
 * (`keys.progress(id)`, `keys.next(id)`) go through {@link useApiQuery} and are
 * best-effort: a failure degrades to an unstarted checklist, never a fatal view
 * error. Sharing those keys with the tree/roadmap reads de-duplicates onto one
 * request and cache entry. Writes are optimistic: `toggle`/`setDeadline` update
 * the cached snapshot via SWR `optimisticData` with `rollbackOnError`; a 409
 * stale-revision surfaces the re-read prompt, any other failure a quiet notice.
 */
export function useProgress(roadmapId: string): {
  checkedIds: Set<string>
  toggle: (itemId: string, checked: boolean) => void
  deadline: string | null
  setDeadline: (deadline: string | null) => void
  /** The current "next" subsection id (from `GET /next`), or null when done. */
  nextSubsectionId: string | null
  /** True once the caller has completed every item in the suggested path. */
  nextComplete: boolean
  /** A surfaced write failure, or null; cleared by `dismissNotice` / `reload`. */
  notice: ProgressNotice | null
  dismissNotice: () => void
  /** Refetch progress + next (the re-read recovery for a stale write). */
  reload: () => void
} {
  const client = useSessionClient()
  const [notice, setNotice] = useState<ProgressNotice | null>(null)

  const { data: progress, mutate: mutateProgress } = useApiQuery(keys.progress(roadmapId), (c) =>
    c.GET('/roadmaps/{roadmap_id}/progress', {
      params: { path: { roadmap_id: roadmapId }, query: { detailed: true } },
    }),
  )
  const { data: next, mutate: mutateNext } = useApiQuery(keys.next(roadmapId), (c) =>
    c.GET('/roadmaps/{roadmap_id}/next', { params: { path: { roadmap_id: roadmapId } } }),
  )

  const checkedIds = useMemo(() => new Set(progress?.checked_ids ?? []), [progress])
  const deadline = progress?.deadline ?? null
  const nextSubsectionId = firstNextSubsectionId(next)
  const nextComplete = next?.complete ?? false

  // runQuery only ever throws a Problem; the rejection crosses the mutate promise
  // as an unknown, so normalize it back to classify the surfaced notice.
  const classifyFailure = useCallback((thrown: unknown) => {
    const problem = toProblem(thrown)
    setNotice(isStaleRevision(problem) ? { kind: 'stale' } : { kind: 'save-failed' })
  }, [])

  const toggle = useCallback(
    (itemId: string, checked: boolean) => {
      setNotice(null)
      void mutateProgress(
        async () => {
          const result = await runQuery(() =>
            client.POST('/roadmaps/{roadmap_id}/progress', {
              params: { path: { roadmap_id: roadmapId } },
              body: { item_ids: [itemId], state: checked ? 'complete' : 'incomplete' },
            }),
          )
          // Reconcile the best-effort next key from the same response so the two
          // keys cannot drift; the returned snapshot commits keys.progress(id).
          void mutateNext(result.next, { revalidate: false })
          return result.progress
        },
        {
          optimisticData: (current) => patchCheckedIds(current, roadmapId, itemId, checked),
          rollbackOnError: true,
          revalidate: false,
        },
      ).catch(classifyFailure)
    },
    [client, roadmapId, mutateProgress, mutateNext, classifyFailure],
  )

  const setDeadline = useCallback(
    (nextDeadline: string | null) => {
      setNotice(null)
      void mutateProgress(
        async (current) => {
          const result = await runQuery(() =>
            client.PUT('/roadmaps/{roadmap_id}/deadline', {
              params: { path: { roadmap_id: roadmapId } },
              body: { deadline: nextDeadline },
            }),
          )
          // The PUT returns a `Progress` record (not a snapshot): fold only its
          // deadline into the cached snapshot rather than overwriting the shape.
          return patchDeadline(current, roadmapId, result.deadline ?? null)
        },
        {
          optimisticData: (current) => patchDeadline(current, roadmapId, nextDeadline),
          rollbackOnError: true,
          revalidate: false,
        },
      ).catch(classifyFailure)
    },
    [client, roadmapId, mutateProgress, classifyFailure],
  )

  const dismissNotice = useCallback(() => setNotice(null), [])
  const reload = useCallback(() => {
    setNotice(null)
    void mutateProgress()
    void mutateNext()
  }, [mutateProgress, mutateNext])

  return {
    checkedIds,
    toggle,
    deadline,
    setDeadline,
    nextSubsectionId,
    nextComplete,
    notice,
    dismissNotice,
    reload,
  }
}
