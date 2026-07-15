import { keys, useApiQuery } from '@/api'
import type { Problem } from '@/lib/problem'

import type { ProgressSnapshot, Roadmap, TreeDataState } from '../types'

/** The subset of an SWR read result the tree mapping consumes. */
interface ReadResult<T> {
  data: T | undefined
  error: Problem | undefined
  isLoading: boolean
}

/**
 * Derive the tree's phase-state from the two reads with their different
 * fatality. The roadmap read is fatal: while it loads the view shows the
 * skeleton, and any failure (or an empty body) is the single error surface. The
 * progress read is best-effort, so only its `data` is read here: any failure
 * collapses to an empty checked set, letting an anonymous viewer (or a public
 * reader with no progress record) still see the tree in its base state.
 */
function toTreeDataState(
  roadmap: ReadResult<Roadmap>,
  progress: Pick<ReadResult<ProgressSnapshot>, 'data'>,
): TreeDataState {
  if (roadmap.isLoading && !roadmap.data) return { phase: 'loading' }
  if (roadmap.error || !roadmap.data) return { phase: 'error' }
  return {
    phase: 'loaded',
    roadmap: roadmap.data,
    checkedIds: new Set(progress.data?.checked_ids ?? []),
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

  return { state: toTreeDataState(roadmap, progress) }
}
