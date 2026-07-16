import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { createHookWrapper } from '@/test/createHookWrapper'

import type { RoadmapCardData } from '../types'
import { useDashboard } from './useDashboard'

function buildCard(overrides: Partial<RoadmapCardData> = {}): RoadmapCardData {
  return {
    id: 'grokking-dsa-7f3k',
    title: 'Grokking DSA',
    status: 'published',
    visibility: 'public',
    subject_tags: ['cs'],
    ...overrides,
  }
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderDashboard(enabled: boolean) {
  return renderHook(() => useDashboard(enabled), { wrapper: createHookWrapper() })
}

describe('useDashboard', () => {
  it('does not fetch when disabled (null key), staying in the loading phase', async () => {
    let fetches = 0
    server.use(
      http.get('*/me/dashboard', () => {
        fetches += 1
        return HttpResponse.json({ authored: [], followed: [] })
      }),
    )
    const { result } = renderDashboard(false)

    // A null key must never fetch; wait past mount so a stray request would land.
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(fetches).toBe(0)
    expect(result.current.state).toEqual({ phase: 'loading' })
  })

  it('resolves to loaded with the authored and followed lists', async () => {
    const authored = [buildCard({ id: 'r-1', title: 'Systems Design' })]
    const followed = [buildCard({ id: 'r-2', title: 'Rust in Practice' })]
    server.use(http.get('*/me/dashboard', () => HttpResponse.json({ authored, followed })))
    const { result } = renderDashboard(true)

    await waitFor(() =>
      expect(result.current.state).toEqual({ phase: 'loaded', authored, followed }),
    )
  })

  it('defaults missing authored/followed lists to empty arrays', async () => {
    server.use(http.get('*/me/dashboard', () => HttpResponse.json({})))
    const { result } = renderDashboard(true)

    await waitFor(() =>
      expect(result.current.state).toEqual({ phase: 'loaded', authored: [], followed: [] }),
    )
  })

  it('surfaces error on a failed read (500)', async () => {
    server.use(http.get('*/me/dashboard', () => new HttpResponse(null, { status: 500 })))
    const { result } = renderDashboard(true)

    await waitFor(() => expect(result.current.state).toEqual({ phase: 'error' }))
  })

  it('surfaces error when the read throws at the network level', async () => {
    server.use(http.get('*/me/dashboard', () => HttpResponse.error()))
    const { result } = renderDashboard(true)

    await waitFor(() => expect(result.current.state).toEqual({ phase: 'error' }))
  })

  it('reloads via mutate, recovering from an error to loaded', async () => {
    server.use(
      http.get('*/me/dashboard', () => new HttpResponse(null, { status: 500 }), { once: true }),
    )
    const { result } = renderDashboard(true)

    await waitFor(() => expect(result.current.state).toEqual({ phase: 'error' }))

    server.use(
      http.get('*/me/dashboard', () => HttpResponse.json({ authored: [buildCard()], followed: [] })),
    )
    act(() => result.current.reload())

    await waitFor(() =>
      expect(result.current.state).toEqual({
        phase: 'loaded',
        authored: [buildCard()],
        followed: [],
      }),
    )
  })
})
