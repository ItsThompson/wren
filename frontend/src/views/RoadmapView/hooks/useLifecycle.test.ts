import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { createSessionClient } from '@/auth/createSessionClient'

import type { Roadmap } from '../types'
import { useLifecycle } from './useLifecycle'

const BASE = 'https://api.test'
const ROADMAP_ID = 'grokking-dsa-7f3k'
const VISIBILITY_URL = `${BASE}/roadmaps/${ROADMAP_ID}/visibility`
const ARCHIVE_URL = `${BASE}/roadmaps/${ROADMAP_ID}:archive`
const DELETE_URL = `${BASE}/roadmaps/${ROADMAP_ID}`

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

/**
 * Render `useLifecycle` with a real session client + fresh `vi.fn()` callbacks
 * and no providers: the hook takes its client and callbacks as params, so it is
 * context-free and needs only MSW to stand in for the network.
 */
function renderLifecycle() {
  const onChanged = vi.fn()
  const onDeleted = vi.fn()
  const client = createSessionClient(BASE)
  const view = renderHook(() => useLifecycle(client, ROADMAP_ID, { onChanged, onDeleted }))
  return { ...view, onChanged, onDeleted }
}

describe('useLifecycle visibility toggle', () => {
  it('reconciles the returned roadmap and returns to idle on success', async () => {
    const updated = buildRoadmap({ visibility: 'public' })
    let put: unknown
    server.use(
      http.put(VISIBILITY_URL, async ({ request }) => {
        put = await request.json()
        return HttpResponse.json(updated)
      }),
    )
    const { result, onChanged } = renderLifecycle()

    act(() => result.current.setVisibility('public'))
    expect(result.current.visibilityState).toEqual({ phase: 'saving' })

    await waitFor(() => expect(result.current.visibilityState).toEqual({ phase: 'idle' }))
    // The request carries the requested visibility (matched by URL + method).
    expect(put).toEqual({ visibility: 'public' })
    // The returned roadmap is handed to the cache reconciler.
    expect(onChanged).toHaveBeenCalledWith(updated)
  })

  it('carries the HTTP status when the toggle fails (500)', async () => {
    server.use(http.put(VISIBILITY_URL, () => new HttpResponse(null, { status: 500 })))
    const { result, onChanged } = renderLifecycle()

    act(() => result.current.setVisibility('public'))

    await waitFor(() =>
      expect(result.current.visibilityState).toEqual({ phase: 'failed', status: 500 }),
    )
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('carries a null status when the toggle throws at the network level', async () => {
    server.use(http.put(VISIBILITY_URL, () => HttpResponse.error()))
    const { result } = renderLifecycle()

    act(() => result.current.setVisibility('public'))

    await waitFor(() =>
      expect(result.current.visibilityState).toEqual({ phase: 'failed', status: null }),
    )
  })
})

describe('useLifecycle archive', () => {
  it('reconciles the archived roadmap and returns to idle on success', async () => {
    const archived = buildRoadmap({ status: 'archived' })
    server.use(http.post(ARCHIVE_URL, () => HttpResponse.json(archived)))
    const { result, onChanged } = renderLifecycle()

    act(() => result.current.archive())
    expect(result.current.archiveState).toEqual({ phase: 'archiving' })

    await waitFor(() => expect(result.current.archiveState).toEqual({ phase: 'idle' }))
    expect(onChanged).toHaveBeenCalledWith(archived)
  })

  it('carries the HTTP status when archive fails (500)', async () => {
    server.use(http.post(ARCHIVE_URL, () => new HttpResponse(null, { status: 500 })))
    const { result, onChanged } = renderLifecycle()

    act(() => result.current.archive())

    await waitFor(() =>
      expect(result.current.archiveState).toEqual({ phase: 'failed', status: 500 }),
    )
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('carries a null status when archive throws at the network level', async () => {
    server.use(http.post(ARCHIVE_URL, () => HttpResponse.error()))
    const { result } = renderLifecycle()

    act(() => result.current.archive())

    await waitFor(() =>
      expect(result.current.archiveState).toEqual({ phase: 'failed', status: null }),
    )
  })
})

describe('useLifecycle delete', () => {
  it('calls onDeleted after a successful delete (204)', async () => {
    server.use(http.delete(DELETE_URL, () => new HttpResponse(null, { status: 204 })))
    const { result, onDeleted } = renderLifecycle()

    act(() => result.current.deleteRoadmap())
    expect(result.current.deleteState).toEqual({ phase: 'deleting' })

    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1))
  })

  it('moves to blocked when the roadmap has followers (409)', async () => {
    server.use(
      http.delete(DELETE_URL, () =>
        HttpResponse.json(
          {
            type: 'x',
            title: 'Conflict with the current state',
            status: 409,
            code: 'DELETE_HAS_FOLLOWERS',
            detail: 'Roadmap has 2 followers; archive it instead.',
          },
          { status: 409, headers: { 'content-type': 'application/problem+json' } },
        ),
      ),
    )
    const { result, onDeleted } = renderLifecycle()

    act(() => result.current.deleteRoadmap())

    await waitFor(() => expect(result.current.deleteState).toEqual({ phase: 'blocked' }))
    // Blocked is not a delete: the caller must not navigate away.
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('carries the HTTP status when delete fails for another reason (500)', async () => {
    server.use(http.delete(DELETE_URL, () => new HttpResponse(null, { status: 500 })))
    const { result, onDeleted } = renderLifecycle()

    act(() => result.current.deleteRoadmap())

    await waitFor(() =>
      expect(result.current.deleteState).toEqual({ phase: 'failed', status: 500 }),
    )
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('carries a null status when delete throws at the network level', async () => {
    server.use(http.delete(DELETE_URL, () => HttpResponse.error()))
    const { result, onDeleted } = renderLifecycle()

    act(() => result.current.deleteRoadmap())

    await waitFor(() =>
      expect(result.current.deleteState).toEqual({ phase: 'failed', status: null }),
    )
    expect(onDeleted).not.toHaveBeenCalled()
  })
})
