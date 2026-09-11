import { useEffect, useRef, useState } from 'react'

import type { RoadmapStatus } from '../types'

/**
 * Re-read progress when a mounted roadmap changes into archived state. A cached
 * published snapshot cannot establish that the caller already follows the
 * archived roadmap, so callers stay non-interactive until this read settles.
 */
export function useArchivedProgressRefresh(
  roadmapStatus: RoadmapStatus | undefined,
  refreshProgress: () => Promise<unknown>,
): boolean {
  const previousStatusRef = useRef(roadmapStatus)
  const refreshProgressRef = useRef(refreshProgress)
  refreshProgressRef.current = refreshProgress
  const [refreshPending, setRefreshPending] = useState(false)
  const transitionedToArchived =
    roadmapStatus === 'archived' && previousStatusRef.current === 'published'

  useEffect(() => {
    if (previousStatusRef.current === roadmapStatus) return
    const previousStatus = previousStatusRef.current
    previousStatusRef.current = roadmapStatus
    if (roadmapStatus !== 'archived' || previousStatus !== 'published') {
      setRefreshPending(false)
      return
    }

    let active = true
    setRefreshPending(true)
    void refreshProgressRef.current()
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
