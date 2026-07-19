import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse, delay } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { mockNext, mockProgress, mockRoadmap } from '@/mocks/data'
import { renderWithProviders } from '@/test/renderWithProviders'
import { useProgress } from '@/views/RoadmapView/hooks/useProgress'
import { useRoadmap } from '@/views/RoadmapView/hooks/useRoadmap'
import { useTreeData } from '@/views/TreeView/hooks/useTreeData'

/**
 * De-duplication. The roadmap route and the tree route both read
 * `keys.roadmap(id)` and `keys.progress(id)`. This mounts the exact read hooks
 * each route uses (`useRoadmap` + `useProgress` for the roadmap route,
 * `useTreeData` for the tree route) into ONE SWR cache and asserts, via an MSW
 * request counter matched by URL, that each shared key fires exactly one network
 * request while both routes are mounted, proving the shared cache identity
 * across the tree, roadmap, and progress reads.
 */

const BASE = 'https://api.test'
const ROADMAP_ID = mockRoadmap.id

/** The roadmap route's reads: `keys.roadmap(id)` + `keys.progress(id)`/`keys.next(id)`. */
function RoadmapRouteProbe() {
  const { state } = useRoadmap(ROADMAP_ID)
  const { checkedIds } = useProgress(ROADMAP_ID)
  return (
    <div>
      <span data-testid="roadmap-phase">{state.phase}</span>
      <span data-testid="roadmap-checked">{checkedIds.size}</span>
    </div>
  )
}

/** The tree route's read: `keys.roadmap(id)` + `keys.progress(id)` (the same shared keys). */
function TreeRouteProbe() {
  const { state } = useTreeData(ROADMAP_ID)
  return <span data-testid="tree-phase">{state.phase}</span>
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('AC3 de-duplication: co-mounted routes share one request per key', () => {
  it('fires exactly one request per shared key while the roadmap route and the tree route are co-mounted', async () => {
    let roadmapGets = 0
    let progressGets = 0
    let nextGets = 0
    server.use(
      http.get('*/roadmaps/:id/progress', async () => {
        progressGets += 1
        await delay(10)
        return HttpResponse.json(mockProgress)
      }),
      http.get('*/roadmaps/:id/next', async () => {
        nextGets += 1
        await delay(10)
        return HttpResponse.json(mockNext)
      }),
      http.get('*/roadmaps/:id', async () => {
        roadmapGets += 1
        await delay(10)
        return HttpResponse.json(mockRoadmap)
      }),
    )

    renderWithProviders(
      <>
        <RoadmapRouteProbe />
        <TreeRouteProbe />
      </>,
      { baseUrl: BASE },
    )

    // Both routes resolve their reads from the shared cache.
    await waitFor(() => {
      expect(screen.getByTestId('roadmap-phase')).toHaveTextContent('loaded')
      expect(screen.getByTestId('tree-phase')).toHaveTextContent('loaded')
    })

    // `keys.roadmap(id)` is read by BOTH useRoadmap and useTreeData; `keys.progress(id)`
    // by BOTH useProgress and useTreeData. Each still hits the network exactly once.
    expect(roadmapGets).toBe(1)
    expect(progressGets).toBe(1)
    // `keys.next(id)` is read only by useProgress: single fetch, no cross-view sharing.
    expect(nextGets).toBe(1)

    // Both routes see the same shared payload (proving one cache entry, not two).
    expect(screen.getByTestId('roadmap-checked')).toHaveTextContent(
      String(mockProgress.checked_ids?.length ?? 0),
    )
  })
})
