import { keys, useApiQuery } from '@/api'
import type { Problem } from '@/lib/problem'

import { useArchivedProgressRefresh } from '@/views/RoadmapView/hooks/useArchivedProgressRefresh'
import type { ProgressReadState } from '@/views/RoadmapView/types'
import type { ProgressSnapshot, Roadmap, TreeDataState } from '../types'

/** The subset of an SWR read result the tree mapping consumes. */
interface ReadResult<T> {
  data: T | undefined
  error: Problem | undefined
  isLoading: boolean
}

/**
 * Derive the tree's phase-state from the two reads with their different
 * fatality. The roadmap read is fatal. Progress remains explicit so loading,
 * closed, and failed reads never claim confirmed completion; the structural
 * tree stays readable.
 */
function toTreeDataState(
  roadmap: ReadResult<Roadmap>,
  progress: ReadResult<ProgressSnapshot>,
  archivedRefreshPending: boolean,
): TreeDataState {
  if (roadmap.isLoading && !roadmap.data) return { phase: 'loading' }
  if (roadmap.error || !roadmap.data) return { phase: 'error' }
  let progressState: ProgressReadState = { phase: 'loading' }
  if (archivedRefreshPending) {
    progressState = { phase: 'loading' }
  } else if (progress.error?.status === 409 && roadmap.data.status === 'archived') {
    progressState = { phase: 'closed' }
  } else if (progress.error) {
    progressState = { phase: 'failed', status: progress.error.status }
  } else if (progress.data) {
    progressState = { phase: 'ready' }
  }
  return {
    phase: 'loaded',
    roadmap: roadmap.data,
    checkedIds: progressState.phase === 'ready' && progress.data ? new Set(progress.data.checked_ids ?? []) : null,
    progressState,
  }
}

/**
 * Fetch everything the tree view needs for one roadmap through two SWR reads:
 * the full roadmap document (subsections + `prereq_ids`, the DAG edges) and the
 * caller's progress snapshot (for done-state). Both bind the shared session
 * client from context (credentials + transparent refresh), so a private draft
 * resolves for its owner and errors for anyone else.
 *
 * The reads share `keys.roadmap(id)` / `keys.progress(id)` with `useRoadmap` and
 * `useProgress`, so views co-mounted on the same roadmap de-duplicate onto one
 * request per key.
 */
export function useTreeData(roadmapId: string): { state: TreeDataState } {
  const roadmap = useApiQuery(keys.roadmap(roadmapId), (client) =>
    client.GET('/roadmaps/{roadmap_id}', { params: { path: { roadmap_id: roadmapId } } }),
  )
  const progress = useApiQuery(keys.progress(roadmapId), (client) =>
    client.GET('/roadmaps/{roadmap_id}/progress', {
      params: { path: { roadmap_id: roadmapId }, query: { detailed: true } },
    }),
  )
  const archivedRefreshPending = useArchivedProgressRefresh(
    roadmap.data?.status,
    progress.mutate,
  )

  return { state: toTreeDataState(roadmap, progress, archivedRefreshPending) }
}
