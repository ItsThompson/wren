import { useState } from 'react'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse, delay } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { keys, swrRevalidationPosture, useApiQuery } from '@/api'
import { mockProgress, mockRoadmap } from '@/mocks/data'
import { renderWithProviders } from '@/test/renderWithProviders'

/**
 * AC-CACHE-04 (SWR posture). Two assertions:
 *
 * 1. The pinned global posture (spec section 07) is exactly as specified. This is
 *    the single source of truth `App.tsx` and `renderWithProviders` both bind.
 * 2. The posture's observable effect on cross-route cache reuse: a WARM key (one
 *    a prior route already fetched) is served from cache with NO background
 *    refetch when a second route mounts it, while a COLD key (never fetched)
 *    still fetches on first mount. `revalidateOnMount:true` preserves today's
 *    "fetch on mount" for cold keys; `dedupingInterval` keeps the warm remount
 *    from firing a redundant request.
 */

const BASE = 'https://api.test'
const ROADMAP_ID = mockRoadmap.id

/** The "roadmap route": reads and thereby warms `keys.roadmap(id)`. */
function RoadmapReadProbe() {
  const { data } = useApiQuery(keys.roadmap(ROADMAP_ID), (client) =>
    client.GET('/roadmaps/{roadmap_id}', { params: { path: { roadmap_id: ROADMAP_ID } } }),
  )
  return <span data-testid="warm-roadmap">{data?.title ?? 'loading'}</span>
}

/** The "tree route": reuses the WARM `keys.roadmap(id)` and cold-fetches `keys.progress(id)`. */
function TreeReadProbe() {
  const roadmap = useApiQuery(keys.roadmap(ROADMAP_ID), (client) =>
    client.GET('/roadmaps/{roadmap_id}', { params: { path: { roadmap_id: ROADMAP_ID } } }),
  )
  const progress = useApiQuery(keys.progress(ROADMAP_ID), (client) =>
    client.GET('/roadmaps/{roadmap_id}/progress', {
      params: { path: { roadmap_id: ROADMAP_ID }, query: { detailed: true } },
    }),
  )
  return (
    <div>
      <span data-testid="tree-roadmap">{roadmap.data?.title ?? '-'}</span>
      <span data-testid="tree-progress">
        {progress.data ? progress.data.checked_ids?.length ?? 0 : 'pending'}
      </span>
    </div>
  )
}

/** Mounts the roadmap route first, then the tree route on demand into the SAME cache. */
function CrossRoute() {
  const [showTree, setShowTree] = useState(false)
  return (
    <div>
      <RoadmapReadProbe />
      {showTree && <TreeReadProbe />}
      <button type="button" onClick={() => setShowTree(true)}>
        mount-tree
      </button>
    </div>
  )
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('AC-CACHE-04 SWR posture', () => {
  it('pins the global revalidation posture to the section 07 values', () => {
    expect(swrRevalidationPosture).toEqual({
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      revalidateIfStale: false,
      revalidateOnMount: true,
      dedupingInterval: 2000,
    })
  })

  it('serves a warm cross-route key from cache without a refetch while a cold key still fetches', async () => {
    let roadmapGets = 0
    let progressGets = 0
    server.use(
      http.get('*/roadmaps/:id/progress', async () => {
        progressGets += 1
        await delay(10)
        return HttpResponse.json(mockProgress)
      }),
      http.get('*/roadmaps/:id', async () => {
        roadmapGets += 1
        await delay(10)
        return HttpResponse.json(mockRoadmap)
      }),
    )

    renderWithProviders(<CrossRoute />, { baseUrl: BASE })

    // The roadmap route fetches the cold key once on first mount.
    await waitFor(() =>
      expect(screen.getByTestId('warm-roadmap')).toHaveTextContent(mockRoadmap.title),
    )
    expect(roadmapGets).toBe(1)

    // Mount the tree route: it reads the now-warm `keys.roadmap(id)` and the cold
    // `keys.progress(id)`.
    fireEvent.click(screen.getByRole('button', { name: 'mount-tree' }))

    // The warm key is served from cache synchronously (no loading placeholder).
    expect(screen.getByTestId('tree-roadmap')).toHaveTextContent(mockRoadmap.title)
    // The cold key fetches on first mount.
    await waitFor(() =>
      expect(screen.getByTestId('tree-progress')).toHaveTextContent(
        String(mockProgress.checked_ids?.length ?? 0),
      ),
    )

    // No background refetch of the warm key (revalidateIfStale:false + dedupe);
    // the cold key fetched exactly once (revalidateOnMount:true).
    expect(roadmapGets).toBe(1)
    expect(progressGets).toBe(1)
  })
})
