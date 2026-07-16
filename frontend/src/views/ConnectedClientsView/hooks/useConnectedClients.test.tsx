import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { createHookWrapper } from '@/test/createHookWrapper'

import type { ConnectedClient } from '../types'
import { useConnectedClients } from './useConnectedClients'

const BASE = 'https://api.test'

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

/** A minimal valid `ConnectedClient` in the OpenAPI-generated shape; override per test. */
function buildClient(overrides: Partial<ConnectedClient> = {}): ConnectedClient {
  return {
    client_id: 'client-abc',
    client_name: 'Claude Desktop',
    scopes: ['roadmaps:read', 'progress:write'],
    last_authorized: '2026-07-10T00:00:00Z',
    ...overrides,
  }
}

/** A second, distinct client used to assert the surviving row after a revoke. */
const otherClient = buildClient({ client_id: 'client-xyz', client_name: 'Research Agent' })

/**
 * Render `useConnectedClients` through the production provider stack: the hook
 * binds the shared session client from `ApiClientProvider` and the shared SWR
 * cache from the wrapper, so a revoke's in-place cache edit is observable through
 * the same read. MSW stands in for the network.
 */
function renderClients(enabled: boolean) {
  return renderHook(() => useConnectedClients(enabled), {
    wrapper: createHookWrapper({ baseUrl: BASE }),
  })
}

describe('useConnectedClients read gating', () => {
  it('never fetches while disabled', async () => {
    let clientsFetches = 0
    server.use(
      http.get('*/me/clients', () => {
        clientsFetches += 1
        return HttpResponse.json([buildClient()])
      }),
    )
    const { result } = renderClients(false)

    // Flush effects: a null key (enabled=false) must produce zero requests.
    await act(async () => {
      await Promise.resolve()
    })
    expect(clientsFetches).toBe(0)
    // The disabled hook stays in its pre-fetch loading phase.
    expect(result.current.state).toEqual({ phase: 'loading' })
  })

  it('exposes the loaded client list once the read resolves', async () => {
    const clients = [buildClient(), otherClient]
    server.use(http.get('*/me/clients', () => HttpResponse.json(clients)))
    const { result } = renderClients(true)

    await waitFor(() => expect(result.current.state.phase).toBe('loaded'))
    expect(result.current.state).toEqual({ phase: 'loaded', clients })
  })
})

describe('useConnectedClients revoke', () => {
  it('removes the revoked client in place without a follow-up GET', async () => {
    let clientsFetches = 0
    let deleted: string | null = null
    server.use(
      http.get('*/me/clients', () => {
        clientsFetches += 1
        return HttpResponse.json([buildClient(), otherClient])
      }),
      http.delete('*/me/clients/:clientId', ({ params }) => {
        deleted = params.clientId as string
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const { result } = renderClients(true)
    await waitFor(() => expect(result.current.state.phase).toBe('loaded'))

    let outcome: boolean | undefined
    await act(async () => {
      outcome = await result.current.revoke('client-abc')
    })

    expect(outcome).toBe(true)
    expect(deleted).toBe('client-abc')
    // The revoked row is dropped by the in-place cache edit (`revalidate: false`).
    await waitFor(() =>
      expect(result.current.state).toEqual({ phase: 'loaded', clients: [otherClient] }),
    )
    // No revalidating GET followed the successful DELETE: only the mount read fired.
    expect(clientsFetches).toBe(1)
  })

  it('keeps the client and returns false when the revoke fails (500)', async () => {
    server.use(
      http.get('*/me/clients', () => HttpResponse.json([buildClient()])),
      http.delete('*/me/clients/:clientId', () => new HttpResponse(null, { status: 500 })),
    )
    const { result } = renderClients(true)
    await waitFor(() => expect(result.current.state.phase).toBe('loaded'))

    let outcome: boolean | undefined
    await act(async () => {
      outcome = await result.current.revoke('client-abc')
    })

    expect(outcome).toBe(false)
    // The row stays: a failed revoke leaves the cache untouched.
    expect(result.current.state).toEqual({ phase: 'loaded', clients: [buildClient()] })
  })

  it('returns false when the revoke throws at the network level', async () => {
    server.use(
      http.get('*/me/clients', () => HttpResponse.json([buildClient()])),
      http.delete('*/me/clients/:clientId', () => HttpResponse.error()),
    )
    const { result } = renderClients(true)
    await waitFor(() => expect(result.current.state.phase).toBe('loaded'))

    let outcome: boolean | undefined
    await act(async () => {
      outcome = await result.current.revoke('client-abc')
    })

    expect(outcome).toBe(false)
    expect(result.current.state).toEqual({ phase: 'loaded', clients: [buildClient()] })
  })
})

describe('useConnectedClients reload', () => {
  it('refetches the client list on reload', async () => {
    let clientsFetches = 0
    server.use(
      http.get('*/me/clients', () => {
        clientsFetches += 1
        return HttpResponse.json([buildClient()])
      }),
    )
    const { result } = renderClients(true)
    await waitFor(() => expect(result.current.state.phase).toBe('loaded'))
    expect(clientsFetches).toBe(1)

    await act(async () => {
      result.current.reload()
    })

    await waitFor(() => expect(clientsFetches).toBe(2))
  })
})
