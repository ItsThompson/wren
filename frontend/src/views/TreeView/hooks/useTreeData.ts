import { useEffect, useMemo, useState } from 'react'

import { createSessionClient } from '@/auth/createSessionClient'

import type { TreeDataState } from '../types'

/**
 * Fetch everything the tree view needs for one roadmap: the full roadmap
 * document (subsections + `prereq_ids`, the graph)
 * and the caller's progress snapshot (for done-state). Uses the session-aware
 * client (credentials + transparent refresh), so a private draft resolves for
 * its owner and returns an error to anyone else.
 *
 * Progress is best-effort: a public reader with no progress record (or an
 * anonymous viewer) still sees the tree with every node in its base state
 * (roots available, the rest locked). Only a failed roadmap fetch is fatal.
 *
 * `baseUrl` is injected (defaulting at the view) so tests can point the client
 * at an MSW server without touching global config.
 */
export function useTreeData(roadmapId: string, baseUrl: string): { state: TreeDataState } {
  const client = useMemo(() => createSessionClient(baseUrl), [baseUrl])
  const [state, setState] = useState<TreeDataState>({ phase: 'loading' })

  useEffect(() => {
    let active = true
    setState({ phase: 'loading' })

    void (async () => {
      try {
        const { data: roadmap } = await client.GET('/roadmaps/{roadmap_id}', {
          params: { path: { roadmap_id: roadmapId } },
        })
        if (!active) return
        if (!roadmap) {
          setState({ phase: 'error' })
          return
        }

        let checkedIds = new Set<string>()
        try {
          const { data: progress } = await client.GET('/roadmaps/{roadmap_id}/progress', {
            params: { path: { roadmap_id: roadmapId }, query: { detailed: true } },
          })
          if (progress?.checked_ids) checkedIds = new Set(progress.checked_ids)
        } catch {
          // No reachable progress record: leave the checked set empty.
        }

        if (!active) return
        setState({ phase: 'loaded', roadmap, checkedIds })
      } catch {
        // Network failure / no reachable backend: surface an error state rather
        // than hang on the loading skeleton.
        if (active) setState({ phase: 'error' })
      }
    })()

    return () => {
      active = false
    }
  }, [client, roadmapId])

  return { state }
}
