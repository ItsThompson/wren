import type { ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, expectTypeOf, it, vi } from 'vitest'
import { SWRConfig } from 'swr'

import type { Problem } from '@/lib/problem'
import { mockProfile } from '@/mocks/data'

import { ApiClientProvider } from '../ApiClientContext'
import { keys } from '../keys'
import { usePublicApiQuery } from './usePublicApiQuery'

const BASE = 'https://api.test'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function wrapper({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <ApiClientProvider baseUrl={BASE}>{children}</ApiClientProvider>
    </SWRConfig>
  )
}

describe('usePublicApiQuery', () => {
  it('fetches via the public client and returns schema-typed data', async () => {
    server.use(http.get('*/users/:handle', () => HttpResponse.json(mockProfile)))

    const { result } = renderHook(
      () =>
        usePublicApiQuery(keys.profile('ada'), (client) =>
          client.GET('/users/{handle}', { params: { path: { handle: 'ada' } } }),
        ),
      { wrapper },
    )

    await waitFor(() => expect(result.current.data).toEqual(mockProfile))
    expect(result.current.error).toBeUndefined()

    // Matches useApiQuery's return shape: schema-typed `data`, `Problem` error.
    expectTypeOf(result.current.data).not.toBeAny()
    expectTypeOf(result.current.data).not.toBeUnknown()
    expectTypeOf(result.current.error).toEqualTypeOf<Problem | undefined>()
  })

  it('reads the public client from context: throws outside an ApiClientProvider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() =>
      renderHook(() =>
        usePublicApiQuery(keys.profile('ada'), (client) =>
          client.GET('/users/{handle}', { params: { path: { handle: 'ada' } } }),
        ),
      ),
    ).toThrow('usePublicClient must be used within an ApiClientProvider')
    spy.mockRestore()
  })

  it('fires no request for a null key and stays in a non-loading idle shape', async () => {
    let calls = 0
    server.use(
      http.get('*/users/:handle', () => {
        calls += 1
        return HttpResponse.json(mockProfile)
      }),
    )

    const { result } = renderHook(
      () =>
        usePublicApiQuery(null, (client) =>
          client.GET('/users/{handle}', { params: { path: { handle: 'ada' } } }),
        ),
      { wrapper },
    )

    expect(result.current.isLoading).toBe(false)
    expect(result.current.data).toBeUndefined()

    await new Promise((resolve) => setTimeout(resolve, 25))
    expect(calls).toBe(0)
  })

  it('surfaces a 404 as a Problem error', async () => {
    server.use(
      http.get('*/users/:handle', () =>
        HttpResponse.json(
          { title: 'Not found', status: 404, code: 'NOT_FOUND' },
          { status: 404, headers: { 'content-type': 'application/problem+json' } },
        ),
      ),
    )

    const { result } = renderHook(
      () =>
        usePublicApiQuery(keys.profile('ghost'), (client) =>
          client.GET('/users/{handle}', { params: { path: { handle: 'ghost' } } }),
        ),
      { wrapper },
    )

    await waitFor(() => expect(result.current.error).toBeDefined())
    expect(result.current.error).toMatchObject({ status: 404, code: 'NOT_FOUND' })
    expect(result.current.data).toBeUndefined()
  })

  it('mutate() revalidates the key', async () => {
    let calls = 0
    server.use(
      http.get('*/users/:handle', () => {
        calls += 1
        return HttpResponse.json(mockProfile)
      }),
    )

    const { result } = renderHook(
      () =>
        usePublicApiQuery(keys.profile('ada'), (client) =>
          client.GET('/users/{handle}', { params: { path: { handle: 'ada' } } }),
        ),
      { wrapper },
    )

    await waitFor(() => expect(result.current.data).toEqual(mockProfile))
    expect(calls).toBe(1)

    await act(async () => {
      await result.current.mutate()
    })

    await waitFor(() => expect(calls).toBe(2))
  })
})
