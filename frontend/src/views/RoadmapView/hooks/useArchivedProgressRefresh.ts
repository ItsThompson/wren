import { useEffect, useRef, useState } from 'react'

import type { RoadmapStatus } from '../types'

/**
 * Re-read progress when a roadmap enters archived state. A cached published
 * snapshot cannot establish that the caller already follows the archived
 * roadmap, so clear it and keep callers non-interactive until the read settles.
 */
export function useArchivedProgressRefresh(
  roadmapStatus: RoadmapStatus | undefined,
  refreshProgress: () => Promise<unknown>,
  invalidateProgress: () => Promise<unknown>,
): boolean {
  const previousStatusRef = useRef<RoadmapStatus | undefined>(undefined)
  const refreshProgressRef = useRef(refreshProgress)
  const invalidateProgressRef = useRef(invalidateProgress)
  refreshProgressRef.current = refreshProgress
  invalidateProgressRef.current = invalidateProgress
  const [refreshPending, setRefreshPending] = useState(false)
  const transitionedToArchived =
    roadmapStatus === 'archived' && previousStatusRef.current !== 'archived'

  useEffect(() => {
    if (previousStatusRef.current === roadmapStatus) return
    previousStatusRef.current = roadmapStatus
    if (roadmapStatus !== 'archived') {
      setRefreshPending(false)
      return
    }

    let active = true
    setRefreshPending(true)
    void invalidateProgressRef.current()
      .finally(() => refreshProgressRef.current())
      .finally(() => {
        if (active) setRefreshPending(false)
      })
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [roadmapStatus])

  return transitionedToArchived || refreshPending
}
