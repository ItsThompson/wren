import type { ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, expectTypeOf, it, vi } from 'vitest'
import { SWRConfig } from 'swr'

import type { Problem } from '@/lib/problem'
import { mockDashboard } from '@/mocks/data'

import { ApiClientProvider } from '../ApiClientContext'
import { keys } from '../keys'
import { useApiQuery } from '../useApiQuery'

const BASE = 'https://api.test'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

/**
 * A fresh SWR cache (own `Map`) per render so state never leaks between tests,
 * wrapping the shared-client provider these hooks bind to. The full cross-test
 * harness lands in ticket #4; these unit tests stay self-contained.
 */
function wrapper({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <ApiClientProvider baseUrl={BASE}>{children}</ApiClientProvider>
    </SWRConfig>
  )
}

describe('useApiQuery', () => {
  it('fetches via the session client and returns schema-typed data', async () => {
    server.use(http.get('*/me/dashboard', () => HttpResponse.json(mockDashboard)))

    const { result } = renderHook(
      () => useApiQuery(keys.dashboard(), (client) => client.GET('/me/dashboard')),
      { wrapper },
    )

    await waitFor(() => expect(result.current.data).toEqual(mockDashboard))
    expect(result.current.error).toBeUndefined()

    // AC7: `data` is inferred from the schema (no `any`/`unknown` leak); `error`
    // is a `Problem`.
    expectTypeOf(result.current.data).not.toBeAny()
    expectTypeOf(result.current.data).not.toBeUnknown()
    expectTypeOf(result.current.error).toEqualTypeOf<Problem | undefined>()
  })

  it('reads the session client from context: throws outside an ApiClientProvider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() =>
      renderHook(() => useApiQuery(keys.dashboard(), (client) => client.GET('/me/dashboard'))),
    ).toThrow('useSessionClient must be used within an ApiClientProvider')
    spy.mockRestore()
  })

  it('fires no request for a null key and stays in a non-loading idle shape', async () => {
    let calls = 0
    server.use(
      http.get('*/me/dashboard', () => {
        calls += 1
        return HttpResponse.json(mockDashboard)
      }),
    )

    const { result } = renderHook(
      () => useApiQuery(null, (client) => client.GET('/me/dashboard')),
      { wrapper },
    )

    expect(result.current.isLoading).toBe(false)
    expect(result.current.data).toBeUndefined()
    expect(result.current.error).toBeUndefined()

    // Give SWR a window to (not) fetch, then confirm no request left the client.
    await new Promise((resolve) => setTimeout(resolve, 25))
    expect(calls).toBe(0)
  })

  it('surfaces a non-ok response as a Problem error', async () => {
    server.use(
      http.get('*/me/dashboard', () =>
        HttpResponse.json(
          { title: 'Server error', status: 500, code: 'INTERNAL' },
          { status: 500, headers: { 'content-type': 'application/problem+json' } },
        ),
      ),
    )

    const { result } = renderHook(
      () => useApiQuery(keys.dashboard(), (client) => client.GET('/me/dashboard')),
      { wrapper },
    )

    await waitFor(() => expect(result.current.error).toBeDefined())
    expect(result.current.error).toMatchObject({ status: 500, code: 'INTERNAL' })
    expect(result.current.data).toBeUndefined()
  })

  it('mutate() revalidates the key', async () => {
    let calls = 0
    server.use(
      http.get('*/me/dashboard', () => {
        calls += 1
        return HttpResponse.json(mockDashboard)
      }),
    )

    const { result } = renderHook(
      () => useApiQuery(keys.dashboard(), (client) => client.GET('/me/dashboard')),
      { wrapper },
    )

    await waitFor(() => expect(result.current.data).toEqual(mockDashboard))
    expect(calls).toBe(1)

    await act(async () => {
      await result.current.mutate()
    })

    await waitFor(() => expect(calls).toBe(2))
  })
})
