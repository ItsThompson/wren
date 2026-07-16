import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { useLocation } from 'react-router'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { createHookWrapper } from '@/test/createHookWrapper'

import type { MetadataDraft, Roadmap } from '../types'
import { useRoadmap } from './useRoadmap'

const BASE = 'https://api.test'
const ROADMAP_ID = 'grokking-dsa-7f3k'
const READ_URL = `${BASE}/roadmaps/${ROADMAP_ID}`
const PUBLISH_URL = `${BASE}/roadmaps/${ROADMAP_ID}:publish`
const METADATA_URL = `${BASE}/roadmaps/${ROADMAP_ID}/metadata`
const FORK_URL = `${BASE}/roadmaps/${ROADMAP_ID}:fork`

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

/** A minimal valid `Roadmap` in the OpenAPI-generated shape; override per test. */
function buildRoadmap(overrides: Partial<Roadmap> = {}): Roadmap {
  return {
    id: ROADMAP_ID,
    owner: 'user-1',
    title: 'Grokking DSA',
    visibility: 'private',
    status: 'draft',
    revision: 1,
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:00Z',
    ...overrides,
  }
}

/** A problem+json 409 body (immutable / stale write conflict). */
function conflict(code: string, detail: string) {
  return HttpResponse.json(
    { type: 'x', title: 'Conflict with the current state', status: 409, code, detail },
    { status: 409, headers: { 'content-type': 'application/problem+json' } },
  )
}

/**
 * Render `useRoadmap` under the production-parity provider stack (fresh-cache
 * SWR + `ApiClientProvider` + auth + router) via the shared `createHookWrapper`.
 * `useLocation` rides along so a fork's navigation is assertable, and the hook's
 * `id` is a render prop so the `roadmapId`-change reset can be exercised on one
 * mounted instance.
 */
function renderRoadmap(initialId: string = ROADMAP_ID) {
  return renderHook(
    ({ id }: { id: string }) => ({ roadmap: useRoadmap(id), location: useLocation() }),
    { initialProps: { id: initialId }, wrapper: createHookWrapper({ baseUrl: BASE }) },
  )
}

/** Render with the read mocked to `roadmap` and wait for the loaded state. */
async function renderLoaded(roadmap: Roadmap = buildRoadmap()) {
  server.use(http.get(READ_URL, () => HttpResponse.json(roadmap)))
  const view = renderRoadmap()
  await waitFor(() =>
    expect(view.result.current.roadmap.state).toEqual({ phase: 'loaded', roadmap }),
  )
  return view
}

describe('useRoadmap read', () => {
  it('resolves the read into the loaded view state', async () => {
    const roadmap = buildRoadmap()
    server.use(http.get(READ_URL, () => HttpResponse.json(roadmap)))
    const { result } = renderRoadmap()

    // Loading until the read resolves, then the loaded roadmap.
    expect(result.current.roadmap.state).toEqual({ phase: 'loading' })
    await waitFor(() =>
      expect(result.current.roadmap.state).toEqual({ phase: 'loaded', roadmap }),
    )
  })
})

describe('useRoadmap publish', () => {
  it('reconciles the published roadmap into the cache and stays idle on 200', async () => {
    const published = buildRoadmap({ status: 'published' })
    server.use(http.post(PUBLISH_URL, () => HttpResponse.json(published)))
    const { result } = await renderLoaded()

    await act(async () => {
      await result.current.roadmap.publish()
    })

    // The returned immutable transition is written into the read cache in place
    // (no refetch), so the view reflects it; the action returns to idle.
    expect(result.current.roadmap.publishState).toEqual({ phase: 'idle' })
    expect(result.current.roadmap.state).toEqual({ phase: 'loaded', roadmap: published })
  })

  it('surfaces the returned violations when publish is hard-blocked (422)', async () => {
    const violation = {
      rule: 'V7_RESOURCE_REQUIRED',
      ids: ['sub_hashing'],
      message: 'subsection sub_hashing has no resources',
    }
    server.use(
      http.post(PUBLISH_URL, () =>
        HttpResponse.json(
          { type: 'x', title: 'Draft cannot be published', status: 422, code: 'VALIDATION', violations: [violation] },
          { status: 422, headers: { 'content-type': 'application/problem+json' } },
        ),
      ),
    )
    const { result } = await renderLoaded()

    await act(async () => {
      await result.current.roadmap.publish()
    })

    expect(result.current.roadmap.publishState).toEqual({ phase: 'blocked', violations: [violation] })
    // A hard-block is not a conflict prompt.
    expect(result.current.roadmap.conflict).toBeNull()
  })

  it('raises the shared conflict prompt and stays idle on a 409', async () => {
    server.use(http.post(PUBLISH_URL, () => conflict('IMMUTABLE', 'Already published; fork to change.')))
    const { result } = await renderLoaded()

    await act(async () => {
      await result.current.roadmap.publish()
    })

    expect(result.current.roadmap.conflict).toMatchObject({ status: 409, code: 'IMMUTABLE' })
    expect(result.current.roadmap.publishState).toEqual({ phase: 'idle' })
  })

  it('carries the HTTP status when publish fails unexpectedly (500)', async () => {
    server.use(http.post(PUBLISH_URL, () => new HttpResponse(null, { status: 500 })))
    const { result } = await renderLoaded()

    await act(async () => {
      await result.current.roadmap.publish()
    })

    expect(result.current.roadmap.publishState).toEqual({ phase: 'failed', status: 500 })
  })

  it('carries a null status when publish throws at the network level', async () => {
    server.use(http.post(PUBLISH_URL, () => HttpResponse.error()))
    const { result } = await renderLoaded()

    await act(async () => {
      await result.current.roadmap.publish()
    })

    // A rejected fetch (distinct from a 4xx/5xx response) yields status: null.
    expect(result.current.roadmap.publishState).toEqual({ phase: 'failed', status: null })
  })
})

describe('useRoadmap editMetadata', () => {
  const draft: MetadataDraft = {
    title: 'Renamed',
    description: 'A prerequisite-aware path.',
    subject_tags: ['cs'],
  }

  it('reconciles the returned roadmap and resolves true on 200', async () => {
    const updated = buildRoadmap({ title: draft.title, subject_tags: draft.subject_tags })
    let patched: unknown
    server.use(
      http.patch(METADATA_URL, async ({ request }) => {
        patched = await request.json()
        return HttpResponse.json(updated)
      }),
    )
    const { result } = await renderLoaded()

    let outcome: boolean | undefined
    await act(async () => {
      outcome = await result.current.roadmap.editMetadata(draft)
    })

    expect(outcome).toBe(true)
    // Only the three presentation fields are sent (matched by URL + method).
    expect(patched).toEqual({
      title: 'Renamed',
      description: 'A prerequisite-aware path.',
      subject_tags: ['cs'],
    })
    expect(result.current.roadmap.metadataState).toEqual({ phase: 'idle' })
    // The header reflects the returned roadmap in place (no refetch).
    expect(result.current.roadmap.state).toEqual({ phase: 'loaded', roadmap: updated })
  })

  it('raises the shared conflict prompt and resolves false on a 409', async () => {
    server.use(http.patch(METADATA_URL, () => conflict('IMMUTABLE', 'Structural field on a published roadmap.')))
    const { result } = await renderLoaded()

    let outcome: boolean | undefined
    await act(async () => {
      outcome = await result.current.roadmap.editMetadata(draft)
    })

    expect(outcome).toBe(false)
    expect(result.current.roadmap.conflict).toMatchObject({ status: 409, code: 'IMMUTABLE' })
    expect(result.current.roadmap.metadataState).toEqual({ phase: 'idle' })
  })

  it('carries the HTTP status and resolves false when the edit fails (500)', async () => {
    server.use(http.patch(METADATA_URL, () => new HttpResponse(null, { status: 500 })))
    const { result } = await renderLoaded()

    let outcome: boolean | undefined
    await act(async () => {
      outcome = await result.current.roadmap.editMetadata(draft)
    })

    expect(outcome).toBe(false)
    expect(result.current.roadmap.metadataState).toEqual({ phase: 'failed', status: 500 })
  })

  it('carries a null status and resolves false when the edit throws', async () => {
    server.use(http.patch(METADATA_URL, () => HttpResponse.error()))
    const { result } = await renderLoaded()

    let outcome: boolean | undefined
    await act(async () => {
      outcome = await result.current.roadmap.editMetadata(draft)
    })

    expect(outcome).toBe(false)
    expect(result.current.roadmap.metadataState).toEqual({ phase: 'failed', status: null })
  })
})

describe('useRoadmap fork', () => {
  it('navigates to the freshly-minted draft on 201', async () => {
    server.use(
      http.post(FORK_URL, () => HttpResponse.json(buildRoadmap({ id: 'grokking-dsa-9x2b' }), { status: 201 })),
    )
    const { result } = await renderLoaded()

    act(() => result.current.roadmap.fork())
    expect(result.current.roadmap.forkState).toEqual({ phase: 'forking' })

    // The fork is a new resource: no cache write, just navigation to its route.
    await waitFor(() =>
      expect(result.current.location.pathname).toBe('/roadmaps/grokking-dsa-9x2b'),
    )
    expect(result.current.roadmap.forkState).toEqual({ phase: 'idle' })
  })

  it('carries the HTTP status and does not navigate when a fork fails (500)', async () => {
    server.use(http.post(FORK_URL, () => new HttpResponse(null, { status: 500 })))
    const { result } = await renderLoaded()

    act(() => result.current.roadmap.fork())

    await waitFor(() =>
      expect(result.current.roadmap.forkState).toEqual({ phase: 'failed', status: 500 }),
    )
    // Stayed on the source route.
    expect(result.current.location.pathname).toBe('/')
  })

  it('carries a null status when a fork throws at the network level', async () => {
    server.use(http.post(FORK_URL, () => HttpResponse.error()))
    const { result } = await renderLoaded()

    act(() => result.current.roadmap.fork())

    await waitFor(() =>
      expect(result.current.roadmap.forkState).toEqual({ phase: 'failed', status: null }),
    )
    expect(result.current.location.pathname).toBe('/')
  })
})

describe('useRoadmap sub-state reset on roadmapId change (R2 invariant)', () => {
  const ROADMAP_B = 'algorithms-ii-9x2b'
  const READ_URL_B = `${BASE}/roadmaps/${ROADMAP_B}`

  // With both `:publish` and `:fork` handlers active, string URLs collide: MSW's
  // path-to-regexp reads a trailing `:word` as a greedy param, so the first
  // matcher would answer both requests. Pin the literal suffix with a regex.
  const PUBLISH_RE = /\/roadmaps\/[^/]+:publish$/
  const FORK_RE = /\/roadmaps\/[^/]+:fork$/

  it('clears the orthogonal action machines when the roadmap id changes', async () => {
    server.use(
      http.get(READ_URL, () => HttpResponse.json(buildRoadmap())),
      http.get(READ_URL_B, () => HttpResponse.json(buildRoadmap({ id: ROADMAP_B }))),
      http.post(PUBLISH_RE, () =>
        HttpResponse.json(
          {
            type: 'x',
            title: 'Draft cannot be published',
            status: 422,
            code: 'VALIDATION',
            violations: [{ rule: 'V7_RESOURCE_REQUIRED', ids: ['sub_hashing'], message: 'no resources' }],
          },
          { status: 422, headers: { 'content-type': 'application/problem+json' } },
        ),
      ),
      http.post(FORK_RE, () => new HttpResponse(null, { status: 500 })),
    )
    const { result, rerender } = renderRoadmap(ROADMAP_ID)
    await waitFor(() => expect(result.current.roadmap.state.phase).toBe('loaded'))

    // Drive two independent action machines out of idle on roadmap A.
    await act(async () => {
      await result.current.roadmap.publish()
    })
    act(() => result.current.roadmap.fork())
    await waitFor(() => {
      expect(result.current.roadmap.publishState.phase).toBe('blocked')
      expect(result.current.roadmap.forkState).toEqual({ phase: 'failed', status: 500 })
    })

    // React Router keeps the same instance across a `:roadmapId` change, so
    // these plain-useState sub-states must be reset or they leak onto roadmap B.
    rerender({ id: ROADMAP_B })

    await waitFor(() => {
      expect(result.current.roadmap.publishState).toEqual({ phase: 'idle' })
      expect(result.current.roadmap.forkState).toEqual({ phase: 'idle' })
      expect(result.current.roadmap.conflict).toBeNull()
    })
  })
})
