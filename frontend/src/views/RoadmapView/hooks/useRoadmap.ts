import { useEffect, useMemo, useState } from 'react'

import { createSessionClient } from '@/auth/createSessionClient'
import type { RoadmapViewState } from '../types'

/**
 * Fetch one roadmap by ID for the owner (section 10 "RoadmapView owns roadmap
 * fetch"). Uses the session-aware client (credentials + transparent refresh), so
 * a private draft resolves for its owner and returns 404/403 to anyone else. The
 * result is a single discriminated `RoadmapViewState`.
 *
 * `baseUrl` is injected (defaulting at the view) so tests can point the client at
 * an MSW server without touching global config.
 */
export function useRoadmap(roadmapId: string, baseUrl: string): { state: RoadmapViewState } {
  const client = useMemo(() => createSessionClient(baseUrl), [baseUrl])
  const [state, setState] = useState<RoadmapViewState>({ phase: 'loading' })

  useEffect(() => {
    let active = true
    setState({ phase: 'loading' })

    void (async () => {
      try {
        const { data, response } = await client.GET('/roadmaps/{roadmap_id}', {
          params: { path: { roadmap_id: roadmapId } },
        })
        if (!active) return
        setState(
          data ? { phase: 'loaded', roadmap: data } : { phase: 'error', status: response.status },
        )
      } catch {
        // Network failure / no reachable backend: surface an error state rather
        // than hang on the loading skeleton.
        if (active) setState({ phase: 'error', status: null })
      }
    })()

    return () => {
      active = false
    }
  }, [client, roadmapId])

  return { state }
}
