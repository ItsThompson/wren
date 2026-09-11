import { useCallback, useEffect, useRef, useState } from 'react'

import type { SessionClient } from '@/api'
import { PROBLEM_CODE, toProblem } from '@/lib/problem'
import type {
  ArchiveState,
  DeleteState,
  Roadmap,
  RoadmapLifecycle,
  Visibility,
  VisibilityState,
} from '../types'

interface LifecycleCallbacks {
  /** Reconcile the shared roadmap cache after a visibility toggle or archive. */
  onChanged: (roadmap: Roadmap) => void
  /** Called after a successful delete: the roadmap is gone, so navigate away. */
  onDeleted: () => void
}

/**
 * The owner-only web-only lifecycle actions for a roadmap:
 * visibility toggle, archive, and delete. Web-only by design: there is no agent
 * (MCP) surface for any of them.
 *
 * Visibility and archive reconcile the loaded roadmap in place via `onChanged`
 * (which writes the returned roadmap into the shared `keys.roadmap(id)` cache in
 * `useRoadmap`, so the badge / discovery state updates without a refetch and any
 * co-mounted reader stays coherent). Delete is guarded by a
 * zero-followers check server-side: a 409 `DELETE_HAS_FOLLOWERS` surfaces as the
 * `blocked` state so the UI can steer the owner to archive instead; a successful
 * delete (204) calls `onDeleted` to leave the now-removed roadmap's route. The
 * shared session `client` and the callbacks are injected so the hook is
 * context-free and testable.
 */
export function useLifecycle(
  client: SessionClient,
  roadmapId: string,
  { onChanged, onDeleted }: LifecycleCallbacks,
): RoadmapLifecycle {
  const [visibilityState, setVisibilityState] = useState<VisibilityState>({ phase: 'idle' })
  const [archiveState, setArchiveState] = useState<ArchiveState>({ phase: 'idle' })
  const [deleteState, setDeleteState] = useState<DeleteState>({ phase: 'idle' })
  const generationRef = useRef(0)
  const previousRoadmapIdRef = useRef(roadmapId)
  const mountedRef = useRef(true)

  if (previousRoadmapIdRef.current !== roadmapId) {
    previousRoadmapIdRef.current = roadmapId
    generationRef.current += 1
  }
  const generation = generationRef.current
  const isCurrent = useCallback(
    () =>
      mountedRef.current &&
      generationRef.current === generation &&
      previousRoadmapIdRef.current === roadmapId,
    [generation, roadmapId],
  )

  useEffect(() => {
    mountedRef.current = true
    setVisibilityState({ phase: 'idle' })
    setArchiveState({ phase: 'idle' })
    setDeleteState({ phase: 'idle' })
    return () => {
      mountedRef.current = false
    }
  }, [roadmapId])

  const setVisibility = useCallback(
    (visibility: Visibility) => {
      setVisibilityState({ phase: 'saving' })
      void (async () => {
        try {
          const { data, response } = await client.PUT('/roadmaps/{roadmap_id}/visibility', {
            params: { path: { roadmap_id: roadmapId } },
            body: { visibility },
          })
          if (!isCurrent()) return
          if (data) {
            onChanged(data)
            setVisibilityState({ phase: 'idle' })
            return
          }
          setVisibilityState({ phase: 'failed', status: response.status })
        } catch {
          if (isCurrent()) setVisibilityState({ phase: 'failed', status: null })
        }
      })()
    },
    [client, roadmapId, onChanged, isCurrent],
  )

  const archive = useCallback(() => {
    setArchiveState({ phase: 'archiving' })
    void (async () => {
      try {
        const { data, response } = await client.POST('/roadmaps/{roadmap_id}:archive', {
          params: { path: { roadmap_id: roadmapId } },
        })
        if (!isCurrent()) return
        if (data) {
          onChanged(data)
          setArchiveState({ phase: 'idle' })
          return
        }
        setArchiveState({ phase: 'failed', status: response.status })
      } catch {
        if (isCurrent()) setArchiveState({ phase: 'failed', status: null })
      }
    })()
  }, [client, roadmapId, onChanged, isCurrent])

  const deleteRoadmap = useCallback(() => {
    setDeleteState({ phase: 'deleting' })
    void (async () => {
      try {
        const { error, response } = await client.DELETE('/roadmaps/{roadmap_id}', {
          params: { path: { roadmap_id: roadmapId } },
        })
        if (!isCurrent()) return
        if (response.ok) {
          onDeleted()
          return
        }
        const problem = toProblem(error, response)
        if (problem.code === PROBLEM_CODE.DeleteHasFollowers) {
          setDeleteState({ phase: 'blocked' })
          return
        }
        setDeleteState({ phase: 'failed', status: response.status })
      } catch {
        if (isCurrent()) setDeleteState({ phase: 'failed', status: null })
      }
    })()
  }, [client, roadmapId, onDeleted, isCurrent])

  return { visibilityState, setVisibility, archiveState, archive, deleteState, deleteRoadmap }
}
