import * as Sentry from '@sentry/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const { withScope } = vi.hoisted(() => ({ withScope: vi.fn() }))
vi.mock('@sentry/react', async (importActual) => ({
  ...(await importActual<typeof import('@sentry/react')>()),
  withScope,
}))

import { handlers } from '@/mocks/handlers'
import { mockDashboard } from '@/mocks/data'
import { createApiReportingMiddleware, operationIdFor } from '@/observability/sentry'

import { createApiClient } from './client'

// The real reporting middleware and report helper run against this mocked SDK
// edge: withScope invokes the scope callback so reporting behavior is observed
// exactly where a synchronous SDK failure would originate.

const server = setupServer(...handlers)
const scopeOps = {
  setTag: vi.fn(),
  setContext: vi.fn(),
  setFingerprint: vi.fn(),
  setLevel: vi.fn(),
}
const captureException = vi.spyOn(Sentry, 'captureException').mockImplementation(() => 'event-1')

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  vi.clearAllMocks()
})
afterAll(() => server.close())
beforeEach(() => {
  withScope.mockImplementation((callback: (scope: typeof scopeOps) => void) => {
    callback(scopeOps)
  })
})

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

  it('skips reporting for validation responses and preserves the response', async () => {
    server.use(http.get('*/me/dashboard', () => new HttpResponse(null, { status: 422 })))
    const client = createApiClient('https://api.test')

    const { response } = await client.GET('/me/dashboard')

    expect(response.status).toBe(422)
    expect(withScope).not.toHaveBeenCalled()
    expect(captureException).not.toHaveBeenCalled()
  })

  it('never replaces a server response when the SDK fails synchronously', async () => {
    withScope.mockImplementationOnce(() => {
      throw new Error('synchronous SDK failure')
    })
    const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    server.use(http.get('*/me/dashboard', () => new HttpResponse(null, { status: 503 })))
    const client = createApiClient('https://api.test')

    const { response } = await client.GET('/me/dashboard')

    expect(response.status).toBe(503)
    expect(consoleWarn).toHaveBeenCalledWith('reporting_failed')
    consoleWarn.mockRestore()
  })

  it('rethrows a network rejection with the original error object', async () => {
    const requestError = new TypeError('offline')
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(requestError)
    const client = createApiClient('https://api.test')

    await expect(client.GET('/me/dashboard')).rejects.toBe(requestError)
    expect(scopeOps.setLevel).toHaveBeenCalledWith('warning')
    expect(scopeOps.setTag).toHaveBeenCalledWith('api.failure_kind', 'network')
    fetchSpy.mockRestore()
  })

  it('never replaces a network rejection when the SDK fails synchronously', async () => {
    withScope.mockImplementationOnce(() => {
      throw new Error('synchronous SDK failure')
    })
    const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const requestError = new TypeError('offline')
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(requestError)
    const client = createApiClient('https://api.test')

    await expect(client.GET('/me/dashboard')).rejects.toBe(requestError)
    expect(consoleWarn).toHaveBeenCalledWith('reporting_failed')
    consoleWarn.mockRestore()
    fetchSpy.mockRestore()
  })

  it('never replaces a raw retry rejection when the SDK fails synchronously', async () => {
    withScope.mockImplementationOnce(() => {
      throw new Error('synchronous SDK failure')
    })
    const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const retryError = new TypeError('raw retry offline')
    const { observeRetryRejection } = createApiReportingMiddleware()

    await expect(
      observeRetryRejection(async () => {
        throw retryError
      }, {
        method: 'GET',
        schemaPath: '/me/dashboard',
        url: 'https://api.test/me/dashboard',
      }),
    ).rejects.toBe(retryError)

    expect(consoleWarn).toHaveBeenCalledWith('reporting_failed')
    consoleWarn.mockRestore()
  })

  it('rejects operation keys that are missing from the generated registry', () => {
    expect(() => operationIdFor('GET', '/unknown')).toThrow('Unknown API operation: GET /unknown')
  })
})
