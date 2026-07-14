import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { handlers } from './handlers'
import {
  mockDashboard,
  mockNext,
  mockProfile,
  mockRoadmap,
} from './data'
import type {
  MockDashboard,
  MockNext,
  MockProfile,
  MockRoadmap,
} from './types'

/**
 * Exercises the dev harness the way the SPA will: through real HTTP against the
 * msw/node server. The `*`-prefixed handler paths must match an absolute API
 * base, so requests go to a fully-qualified host.
 */
const server = setupServer(...handlers)
const base = 'https://api.test'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('mock handlers', () => {
  it('serves the dashboard projection', async () => {
    const response = await fetch(`${base}/me/dashboard`)
    expect(response.status).toBe(200)
    const body = (await response.json()) as MockDashboard
    expect(body).toEqual(mockDashboard)
    expect(body.authored.length).toBeGreaterThan(0)
  })

  it('serves the full roadmap for a known id', async () => {
    const response = await fetch(`${base}/roadmaps/${mockRoadmap.id}`)
    expect(response.status).toBe(200)
    const body = (await response.json()) as MockRoadmap
    expect(body.id).toBe(mockRoadmap.id)
    expect(body.sections).toHaveLength(mockRoadmap.sections.length)
  })

  it('serves the next item in path order', async () => {
    const response = await fetch(`${base}/roadmaps/${mockRoadmap.id}/next`)
    const body = (await response.json()) as MockNext
    expect(body).toEqual(mockNext)
    expect(body.complete).toBe(false)
  })

  it('serves a public profile for a known handle', async () => {
    const response = await fetch(`${base}/users/${mockProfile.handle}`)
    const body = (await response.json()) as MockProfile
    expect(body.handle).toBe(mockProfile.handle)
  })

  it('returns an RFC 9457 problem for an unknown roadmap', async () => {
    const response = await fetch(`${base}/roadmaps/does-not-exist`)
    expect(response.status).toBe(404)
    expect(response.headers.get('content-type')).toContain(
      'application/problem+json',
    )
    const body = (await response.json()) as { code: string; status: number }
    expect(body.code).toBe('NOT_FOUND')
    expect(body.status).toBe(404)
  })

  it('returns an updated progress snapshot on write', async () => {
    const response = await fetch(`${base}/roadmaps/${mockRoadmap.id}/progress`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ checked_item_ids: ['item_hashing_drill'] }),
    })
    expect(response.status).toBe(200)
    const body = (await response.json()) as {
      progress: { roadmap_id: string }
      next: MockNext
    }
    expect(body.progress.roadmap_id).toBe(mockRoadmap.id)
    expect(body.next.roadmap_id).toBe(mockRoadmap.id)
  })
})
