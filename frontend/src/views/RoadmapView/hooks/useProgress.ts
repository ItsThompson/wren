import { useCallback, useMemo, useState } from 'react'

import { keys, runQuery, useApiQuery, useSessionClient } from '@/api'
import { isStaleRevision, toProblem } from '@/lib/problem'
import { firstNextSubsectionId, patchCheckedIds, patchDeadline } from '../util/progress-derive'
import type { ProgressNotice } from '../types'

/**
 * Fetch and mutate the caller's progress for one published roadmap. The two
 * reads derive from {@link useApiQuery} on the shared session client (credentials
 * + transparent refresh), so the record resolves for the signed-in user and is
 * scoped to them server-side; both are best-effort (a failure leaves an unstarted
 * checklist / nothing highlighted, never a fatal view error).
 *
 * `keys.progress(id)` (the detailed snapshot) seeds `checkedIds` and the per-user
 * `deadline`; `keys.next(id)` (`GET /next`) seeds the current "next" subsection
 * (highlighted in the list view) plus the `complete` flag (the calm all-caught-up
 * state). Sharing these exact keys with the tree/roadmap reads means a co-mounted
 * view de-duplicates onto one request and one cache entry.
 *
 * The writes are the only genuinely optimistic slice. `toggle` reflects the
 * check/uncheck instantly via SWR `optimisticData` on `keys.progress(id)`, persists
 * the explicit-set via `POST /progress`, and reconciles BOTH the progress and next
 * keys from the single response; on failure `rollbackOnError` reverts the checked
 * set and a `notice` is surfaced (a 409 stale-revision becomes the re-read prompt,
 * anything else a quiet inline notice) instead of failing silently. `setDeadline`
 * mirrors this on the deadline (folded into the same cached snapshot so the two
 * optimistic surfaces share one entry), and `reload` refetches both keys for the
 * re-read recovery. The client base URL comes from `ApiClientProvider`, so the
 * hook threads no `baseUrl`.
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
