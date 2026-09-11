import { useCallback, useMemo, useRef, useState } from 'react'

import { keys, runQuery, useApiQuery, useSessionClient } from '@/api'
import { isStaleRevision, toProblem } from '@/lib/problem'
import { firstNextSubsectionId, patchCheckedIds, patchDeadline } from '../util/progress-derive'
import type { ProgressNotice, ProgressReadState, RoadmapStatus } from '../types'

/**
 * Fetch and mutate the caller's progress for one published or archived roadmap.
 * The progress read exposes loading, ready, closed, and failed states so an
 * unavailable record is never presented as an empty record. Sharing the keys
 * with the tree view de-duplicates onto one request and cache entry. Writes are
 * optimistic and are enabled only in the ready state.
 */
export function useProgress(roadmapId: string, roadmapStatus: RoadmapStatus = 'published'): {
  /** Null until the server confirms a progress snapshot. */
  checkedIds: Set<string> | null
  progressState: ProgressReadState
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
  const generationRef = useRef(0)
  const previousRoadmapRef = useRef(`${roadmapId}:${roadmapStatus}`)
  const roadmapKey = `${roadmapId}:${roadmapStatus}`
  if (previousRoadmapRef.current !== roadmapKey) {
    previousRoadmapRef.current = roadmapKey
    generationRef.current += 1
  }
  const generation = generationRef.current
  const isCurrent = useCallback(
    () => generationRef.current === generation && previousRoadmapRef.current === roadmapKey,
    [generation, roadmapKey],
  )

  const {
    data: progress,
    error: progressError,
    mutate: mutateProgress,
  } = useApiQuery(keys.progress(roadmapId), (c) =>
    c.GET('/roadmaps/{roadmap_id}/progress', {
      params: { path: { roadmap_id: roadmapId }, query: { detailed: true } },
    }),
  )
  const { data: next, error: nextError, mutate: mutateNext } = useApiQuery(keys.next(roadmapId), (c) =>
    c.GET('/roadmaps/{roadmap_id}/next', { params: { path: { roadmap_id: roadmapId } } }),
  )

  const progressState = useMemo<ProgressReadState>(() => {
    if (roadmapStatus === 'archived' && progressError?.status === 409) return { phase: 'closed' }
    if (progressError) return { phase: 'failed', status: progressError.status }
    if (progress) return { phase: 'ready' }
    return { phase: 'loading' }
  }, [progress, progressError, roadmapStatus])
  const checkedIds = useMemo(
    () => (progressState.phase === 'ready' && progress ? new Set(progress.checked_ids ?? []) : null),
    [progress, progressState.phase],
  )
  const deadline = progress?.deadline ?? null
  const nextSubsectionId = progressState.phase === 'ready' && !nextError ? firstNextSubsectionId(next) : null
  const nextComplete = progressState.phase === 'ready' && !nextError && next?.complete === true

  // runQuery only ever throws a Problem; the rejection crosses the mutate promise
  // as an unknown, so normalize it back to classify the surfaced notice.
  const classifyFailure = useCallback(
    (thrown: unknown) => {
      if (!isCurrent()) return
      const problem = toProblem(thrown)
      setNotice(isStaleRevision(problem) ? { kind: 'stale' } : { kind: 'save-failed' })
    },
    [isCurrent],
  )

  const toggle = useCallback(
    (itemId: string, checked: boolean) => {
      if (!isCurrent() || progressState.phase !== 'ready') return
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
    [client, roadmapId, mutateProgress, mutateNext, classifyFailure, progressState.phase, isCurrent],
  )

  const setDeadline = useCallback(
    (nextDeadline: string | null) => {
      if (!isCurrent() || progressState.phase !== 'ready') return
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
    [client, roadmapId, mutateProgress, classifyFailure, progressState.phase, isCurrent],
  )

  const dismissNotice = useCallback(() => setNotice(null), [])
  const reload = useCallback(() => {
    setNotice(null)
    void mutateProgress()
    void mutateNext()
  }, [mutateProgress, mutateNext])

  return {
    checkedIds,
    progressState,
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
