import { useCallback, useState } from 'react'
import type { Client } from 'openapi-fetch'

import type { paths } from '@/api'
import type {
  ArchiveState,
  DeleteState,
  Roadmap,
  RoadmapLifecycle,
  Visibility,
  VisibilityState,
} from '../types'

interface LifecycleCallbacks {
  /** Replace the loaded roadmap after a visibility toggle or archive (in place). */
  onChanged: (roadmap: Roadmap) => void
  /** Called after a successful delete: the roadmap is gone, so navigate away. */
  onDeleted: () => void
}

/**
 * The owner-only web-only lifecycle actions for a roadmap:
 * visibility toggle, archive, and delete. Web-only by design: there is no agent
 * (MCP) surface for any of them.
 *
 * Visibility and archive replace the loaded roadmap in place via `onChanged` (so
 * the badge / discovery state updates without a refetch). Delete is guarded by a
 * zero-followers check server-side: a 409 `DELETE_HAS_FOLLOWERS` surfaces as the
 * `blocked` state so the UI can steer the owner to archive instead; a successful
 * delete (204) calls `onDeleted` to leave the now-removed roadmap's route. The
 * `client` and callbacks are injected so the hook is context-free and testable.
 */
export function useLifecycle(
  client: Client<paths>,
  roadmapId: string,
  { onChanged, onDeleted }: LifecycleCallbacks,
): RoadmapLifecycle {
  const [visibilityState, setVisibilityState] = useState<VisibilityState>({ phase: 'idle' })
  const [archiveState, setArchiveState] = useState<ArchiveState>({ phase: 'idle' })
  const [deleteState, setDeleteState] = useState<DeleteState>({ phase: 'idle' })

  const setVisibility = useCallback(
    (visibility: Visibility) => {
      setVisibilityState({ phase: 'saving' })
      void (async () => {
        try {
          const { data, response } = await client.PUT('/roadmaps/{roadmap_id}/visibility', {
            params: { path: { roadmap_id: roadmapId } },
            body: { visibility },
          })
          if (data) {
            onChanged(data)
            setVisibilityState({ phase: 'idle' })
            return
          }
          setVisibilityState({ phase: 'failed', status: response.status })
        } catch {
          setVisibilityState({ phase: 'failed', status: null })
        }
      })()
    },
    [client, roadmapId, onChanged],
  )

  const archive = useCallback(() => {
    setArchiveState({ phase: 'archiving' })
    void (async () => {
      try {
        const { data, response } = await client.POST('/roadmaps/{roadmap_id}:archive', {
          params: { path: { roadmap_id: roadmapId } },
        })
        if (data) {
          onChanged(data)
          setArchiveState({ phase: 'idle' })
          return
        }
        setArchiveState({ phase: 'failed', status: response.status })
      } catch {
        setArchiveState({ phase: 'failed', status: null })
      }
    })()
  }, [client, roadmapId, onChanged])

  const deleteRoadmap = useCallback(() => {
    setDeleteState({ phase: 'deleting' })
    void (async () => {
      try {
        const { response } = await client.DELETE('/roadmaps/{roadmap_id}', {
          params: { path: { roadmap_id: roadmapId } },
        })
        if (response.ok) {
          onDeleted()
          return
        }
        if (response.status === 409) {
          // DELETE_HAS_FOLLOWERS: the roadmap has followers, so delete is refused;
          // the UI offers archive as the safe retirement path instead.
          setDeleteState({ phase: 'blocked' })
          return
        }
        setDeleteState({ phase: 'failed', status: response.status })
      } catch {
        setDeleteState({ phase: 'failed', status: null })
      }
    })()
  }, [client, roadmapId, onDeleted])

  return { visibilityState, setVisibility, archiveState, archive, deleteState, deleteRoadmap }
}
