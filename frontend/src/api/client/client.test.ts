import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const { reportApiFailure } = vi.hoisted(() => ({ reportApiFailure: vi.fn() }))
vi.mock('@/observability/sentry', () => ({ reportApiFailure }))

import { createApiClient, operationIdFor } from './client'
import { handlers } from '@/mocks/handlers'
import { mockDashboard } from '@/mocks/data'

/**
 * `/me/dashboard` is a real schema route (`schema.d.ts`), so the factory returns
 * a genuine `Client<paths>` whose `.GET('/me/dashboard')` type-checks against the
 * generated schema with no cast. This proves the factory wires openapi-fetch: it
 * issues a request to the configured base URL and parses the JSON response.
 */

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
beforeEach(() => vi.clearAllMocks())

describe('createApiClient', () => {
  it('issues typed credential-free requests against the configured base URL', async () => {
    let credentials: RequestCredentials | undefined
    server.use(
      http.get('*/me/dashboard', ({ request }) => {
        credentials = request.credentials
        return HttpResponse.json(mockDashboard)
      }),
    )
    const client = createApiClient('https://api.test')

    const { data, response } = await client.GET('/me/dashboard')

    expect(response.status).toBe(200)
    expect(data).toEqual(mockDashboard)
    expect(credentials).toBe('omit')
  })

  it('reports a retried 5xx response exactly once after refresh succeeds', async () => {
    let requestCount = 0
    server.use(
      http.get('*/me/dashboard', () => {
        requestCount += 1
        return requestCount === 1
          ? new HttpResponse(null, { status: 401 })
          : new HttpResponse(null, { status: 503 })
      }),
    )
    const retryOnUnauthorized = vi.fn(async () => true)
    const client = createApiClient('https://api.test', { retryOnUnauthorized })

    const { response } = await client.GET('/me/dashboard')

    expect(response.status).toBe(503)
    expect(retryOnUnauthorized).toHaveBeenCalledOnce()
    expect(reportApiFailure).toHaveBeenCalledOnce()
    expect(reportApiFailure).toHaveBeenCalledWith({
      status: 503,
      operationId: 'get_dashboard_me_dashboard_get',
      method: 'GET',
      url: 'https://api.test/me/dashboard',
    })
  })

  it('rethrows a retried network failure with the original error object', async () => {
    const originalFetch = globalThis.fetch
    const requestError = new TypeError('offline')
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    fetchMock
      .mockImplementationOnce((input, init) => originalFetch(input, init))
      .mockRejectedValueOnce(requestError)

    server.use(http.get('*/me/dashboard', () => new HttpResponse(null, { status: 401 })))
    const client = createApiClient('https://api.test', { retryOnUnauthorized: async () => true })

    await expect(client.GET('/me/dashboard')).rejects.toBe(requestError)
    expect(reportApiFailure).toHaveBeenCalledOnce()
    expect(reportApiFailure).toHaveBeenCalledWith({
      error: requestError,
      status: null,
      operationId: 'get_dashboard_me_dashboard_get',
      method: 'GET',
      url: 'https://api.test/me/dashboard',
    })
    fetchMock.mockRestore()
  })

  it('rejects operation keys that are missing from the generated registry', () => {
    expect(() => operationIdFor('GET', '/unknown')).toThrow('Unknown API operation: GET /unknown')
  })
})
