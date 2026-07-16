import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { createHookWrapper } from '@/test/createHookWrapper'

import { useConsent } from './useConsent'

const BASE = 'https://api.test'
const AUTH_REQUEST_ID = 'req-123'
const APPROVE_REDIRECT = 'http://127.0.0.1:52001/callback?code=abc&state=xyz'
/** The generic decision-failure copy the hook surfaces (mirrors the source). */
const GENERIC_ERROR = 'Something went wrong. Please try again.'

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

/** The parked-request context read: the known id resolves, anything else is 404. */
const contextOk = () =>
  http.get('*/authorize/context', ({ request }) => {
    const id = new URL(request.url).searchParams.get('auth_request_id')
    if (id !== AUTH_REQUEST_ID) return new HttpResponse(null, { status: 404 })
    return HttpResponse.json({
      client_name: 'Claude Desktop',
      scopes: ['roadmaps:read', 'progress:write'],
      authenticated: true,
    })
  })

/**
 * Render `useConsent` through the production provider stack with an injected
 * `navigateExternal` spy, so the browser navigation is asserted without a real
 * redirect. The hook binds the shared session client from `ApiClientProvider`;
 * MSW stands in for the network.
 */
function renderConsent(authRequestId: string) {
  const navigateExternal = vi.fn()
  const view = renderHook(() => useConsent(authRequestId, navigateExternal), {
    wrapper: createHookWrapper({ baseUrl: BASE }),
  })
  return { ...view, navigateExternal }
}

describe('useConsent context read', () => {
  it('reports error and never fetches when the auth_request_id is empty', async () => {
    let contextFetches = 0
    server.use(
      http.get('*/authorize/context', () => {
        contextFetches += 1
        return HttpResponse.json({ client_name: 'x', scopes: [], authenticated: true })
      }),
    )
    const { result } = renderConsent('')

    // A null SWR key means the read never fires; the view falls straight to the
    // expired presentation (`error`).
    expect(result.current.context).toEqual({ phase: 'error' })
    // Flush effects: a null key must still produce zero requests.
    await act(async () => {
      await Promise.resolve()
    })
    expect(contextFetches).toBe(0)
  })

  it('exposes the parked request context once the read resolves', async () => {
    server.use(contextOk())
    const { result } = renderConsent(AUTH_REQUEST_ID)

    await waitFor(() =>
      expect(result.current.context).toEqual({
        phase: 'loaded',
        clientName: 'Claude Desktop',
        scopes: ['roadmaps:read', 'progress:write'],
      }),
    )
  })
})

describe('useConsent decision', () => {
  it('navigates the browser to the returned loopback URL on a decision', async () => {
    server.use(
      contextOk(),
      http.post('*/authorize/decision', () =>
        HttpResponse.json({ redirect_uri: APPROVE_REDIRECT }),
      ),
    )
    const { result, navigateExternal } = renderConsent(AUTH_REQUEST_ID)
    await waitFor(() => expect(result.current.context.phase).toBe('loaded'))

    await act(async () => {
      await result.current.decide(true)
    })

    expect(navigateExternal).toHaveBeenCalledWith(APPROVE_REDIRECT)
  })

  it('collapses the whole view to expired when a decision reports the request gone (404)', async () => {
    server.use(
      contextOk(),
      http.post('*/authorize/decision', () => new HttpResponse(null, { status: 404 })),
    )
    const { result, navigateExternal } = renderConsent(AUTH_REQUEST_ID)
    await waitFor(() => expect(result.current.context.phase).toBe('loaded'))

    await act(async () => {
      await result.current.decide(true)
    })

    // The decision 404 flips the expired gate, so the context collapses to
    // `error` even though the read itself succeeded.
    expect(result.current.context).toEqual({ phase: 'error' })
    expect(navigateExternal).not.toHaveBeenCalled()
  })

  it('surfaces a generic decision error on a 500', async () => {
    server.use(
      contextOk(),
      http.post('*/authorize/decision', () => new HttpResponse(null, { status: 500 })),
    )
    const { result, navigateExternal } = renderConsent(AUTH_REQUEST_ID)
    await waitFor(() => expect(result.current.context.phase).toBe('loaded'))

    await act(async () => {
      await result.current.decide(true)
    })

    expect(result.current.decision).toEqual({ status: 'error', message: GENERIC_ERROR })
    expect(navigateExternal).not.toHaveBeenCalled()
  })

  it('surfaces a generic decision error when the decision throws at the network level', async () => {
    server.use(
      contextOk(),
      http.post('*/authorize/decision', () => HttpResponse.error()),
    )
    const { result, navigateExternal } = renderConsent(AUTH_REQUEST_ID)
    await waitFor(() => expect(result.current.context.phase).toBe('loaded'))

    await act(async () => {
      await result.current.decide(true)
    })

    expect(result.current.decision).toEqual({ status: 'error', message: GENERIC_ERROR })
    expect(navigateExternal).not.toHaveBeenCalled()
  })
})
