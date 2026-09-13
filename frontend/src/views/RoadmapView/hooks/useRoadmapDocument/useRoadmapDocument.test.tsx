import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import type { Roadmap } from '../../types'
import { buildAuthUser, buildAuthValue } from '@/test/auth-harness'
import { createHookWrapper } from '@/test/createHookWrapper'
import { useRoadmapDocument } from './useRoadmapDocument'

const ROADMAP_ID = 'public-roadmap-7f3k'
const roadmap: Roadmap = {
  id: ROADMAP_ID,
  owner: 'owner-1',
  title: 'Public roadmap',
  visibility: 'public',
  status: 'published',
  revision: 1,
  created_at: '2026-07-15T00:00:00Z',
  updated_at: '2026-07-15T00:00:00Z',
}
const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('useRoadmapDocument', () => {
  it('uses the public client for an anonymous reader', async () => {
    let credentials: RequestCredentials | undefined
    server.use(
      http.get('*/roadmaps/:roadmapId', ({ request }) => {
        credentials = request.credentials
        return HttpResponse.json(roadmap)
      }),
    )

    const { result } = renderHook(() => useRoadmapDocument(ROADMAP_ID), {
      wrapper: createHookWrapper(),
    })

    await waitFor(() => expect(result.current.data).toEqual(roadmap))
    expect(credentials).toBe('omit')
  })

  it('uses the session client for an authenticated reader', async () => {
    server.use(http.get('*/roadmaps/:roadmapId', () => HttpResponse.json(roadmap)))
    const { result } = renderHook(() => useRoadmapDocument(ROADMAP_ID), {
      wrapper: createHookWrapper({
        authValue: buildAuthValue({
          status: 'authenticated',
          user: buildAuthUser({ id: 'reader-1' }),
        }),
      }),
    })

    await waitFor(() => expect(result.current.data).toEqual(roadmap))
  })
})
