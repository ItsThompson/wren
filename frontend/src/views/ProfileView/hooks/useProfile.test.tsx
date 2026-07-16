import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { createHookWrapper } from '@/test/createHookWrapper'

import type { ProfileData } from '../types'
import { useProfile } from './useProfile'

const HANDLE = 'ada'

function buildProfile(overrides: Partial<ProfileData> = {}): ProfileData {
  return {
    handle: HANDLE,
    display_name: 'Ada Lovelace',
    roadmaps: [
      {
        id: 'grokking-dsa-7f3k',
        title: 'Grokking DSA',
        status: 'published',
        visibility: 'public',
        subject_tags: ['cs'],
      },
    ],
    ...overrides,
  }
}

/** RFC 9457 problem-details 404 for an unknown handle. */
function notFound(handle: string) {
  return HttpResponse.json(
    {
      type: 'https://usewren.com/errors/not-found',
      title: 'Profile not found',
      status: 404,
      code: 'NOT_FOUND',
      instance: `/users/${handle}`,
    },
    { status: 404, headers: { 'content-type': 'application/problem+json' } },
  )
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// The default anonymous wrapper fires no auth network: `useProfile` reads through
// the credential-free public client, so no session is needed.
function renderProfile(handle = HANDLE) {
  return renderHook(() => useProfile(handle), { wrapper: createHookWrapper() })
}

describe('useProfile', () => {
  it('resolves to loaded with the fetched profile', async () => {
    const profile = buildProfile()
    server.use(http.get('*/users/:handle', () => HttpResponse.json(profile)))
    const { result } = renderProfile()

    await waitFor(() => expect(result.current.state).toEqual({ phase: 'loaded', profile }))
  })

  it('maps a 404 to the first-class notfound state', async () => {
    server.use(http.get('*/users/:handle', ({ params }) => notFound(params.handle as string)))
    const { result } = renderProfile('nobody')

    await waitFor(() => expect(result.current.state).toEqual({ phase: 'notfound' }))
  })

  it('maps a 500 to the generic error state', async () => {
    server.use(http.get('*/users/:handle', () => new HttpResponse(null, { status: 500 })))
    const { result } = renderProfile()

    await waitFor(() => expect(result.current.state).toEqual({ phase: 'error' }))
  })

  it('maps a network-level throw to the generic error state', async () => {
    server.use(http.get('*/users/:handle', () => HttpResponse.error()))
    const { result } = renderProfile()

    await waitFor(() => expect(result.current.state).toEqual({ phase: 'error' }))
  })

  it('reloads via mutate, picking up a changed profile body', async () => {
    let fetches = 0
    const first = buildProfile({ display_name: 'Ada Lovelace' })
    const second = buildProfile({ display_name: 'Ada L.' })
    server.use(
      http.get('*/users/:handle', () => {
        fetches += 1
        return HttpResponse.json(fetches === 1 ? first : second)
      }),
    )
    const { result } = renderProfile()

    await waitFor(() => expect(result.current.state).toEqual({ phase: 'loaded', profile: first }))

    act(() => result.current.reload())

    await waitFor(() => expect(result.current.state).toEqual({ phase: 'loaded', profile: second }))
    expect(fetches).toBe(2)
  })
})
