import * as Sentry from '@sentry/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { beforeSendSentryEvent } from '@/observability/sentry'
import { mockDashboard } from '@/mocks/data'
import { TEST_SENTRY_DSN, makeRecordingTransport } from '@/test/sentryRecording'

import { createSessionClient } from './createSessionClient'

const BASE = 'https://api.test'

const server = setupServer()

const events: Sentry.Event[] = []

function initRecordingTransport(): void {
  Sentry.init({
    dsn: TEST_SENTRY_DSN,
    transport: makeRecordingTransport(events),
    beforeSend: beforeSendSentryEvent,
    sendDefaultPii: false,
    defaultIntegrations: [],
    integrations: [Sentry.linkedErrorsIntegration()],
    enableLogs: false,
    maxBreadcrumbs: 0,
    tracesSampleRate: 0,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
  })
}

const REFRESH_OK = () =>
  http.post('*/auth/refresh', () =>
    HttpResponse.json({ id: 'u', username: 'ada', email: 'a@b.com', created_at: 'x' }),
  )

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
beforeEach(() => {
  events.length = 0
  initRecordingTransport()
})
afterEach(async () => {
  server.resetHandlers()
  await Sentry.close()
})
afterAll(() => server.close())

describe('createSessionClient transparent refresh', () => {
  it('refreshes once and retries the original request on a 401', async () => {
    let dashboardCalls = 0
    let refreshCalls = 0
    server.use(
      http.get('*/me/dashboard', () => {
        dashboardCalls += 1
        // Expired session on first hit; the rotated cookie succeeds on retry.
        return dashboardCalls === 1
          ? new HttpResponse(null, { status: 401 })
          : HttpResponse.json(mockDashboard)
      }),
      http.post('*/auth/refresh', () => {
        refreshCalls += 1
        return HttpResponse.json({ id: 'u', username: 'ada', email: 'a@b.com', created_at: 'x' })
      }),
    )

    const { data, response } = await createSessionClient(BASE).GET('/me/dashboard')

    expect(response.status).toBe(200)
    expect(data).toEqual(mockDashboard)
    expect(refreshCalls).toBe(1)
    expect(dashboardCalls).toBe(2)
  })

  it('coalesces concurrent 401 responses into one refresh request', async () => {
    let refreshCalls = 0
    let dashboardCalls = 0
    server.use(
      http.get('*/me/dashboard', async () => {
        dashboardCalls += 1
        if (dashboardCalls <= 2) return new HttpResponse(null, { status: 401 })
        return HttpResponse.json(mockDashboard)
      }),
      http.post('*/auth/refresh', async () => {
        refreshCalls += 1
        await new Promise((resolve) => setTimeout(resolve, 5))
        return HttpResponse.json({ id: 'u', username: 'ada', email: 'a@b.com', created_at: 'x' })
      }),
    )

    const client = createSessionClient(BASE)
    const results = await Promise.all([client.GET('/me/dashboard'), client.GET('/me/dashboard')])

    expect(results.every(({ response }) => response.ok)).toBe(true)
    expect(refreshCalls).toBe(1)
    expect(dashboardCalls).toBe(4)
  })

  it('does not retry when the refresh itself fails', async () => {
    let dashboardCalls = 0
    server.use(
      http.get('*/me/dashboard', () => {
        dashboardCalls += 1
        return new HttpResponse(null, { status: 401 })
      }),
      http.post('*/auth/refresh', () => new HttpResponse(null, { status: 401 })),
    )

    const { response } = await createSessionClient(BASE).GET('/me/dashboard')
    await Sentry.flush()

    // The original 401 is returned; the refresh 401 does not recurse.
    expect(response.status).toBe(401)
    expect(dashboardCalls).toBe(1)
    // The final 401 is expected and never reaches the transport.
    expect(events).toHaveLength(0)
  })

  it('replays a consumed POST body after refresh, including its identity field', async () => {
    const body = { title: 'Retry create', proposed_id: 'post-retry-id', published_visibility: 'private' as const }
    const receivedBodies: unknown[] = []
    const receivedRequests: Request[] = []
    let requestCount = 0
    server.use(
      http.post('*/roadmaps', async ({ request }) => {
        receivedRequests.push(request)
        receivedBodies.push(await request.json())
        requestCount += 1
        return requestCount === 1
          ? new HttpResponse(null, { status: 401 })
          : HttpResponse.json({}, { status: 201 })
      }),
      REFRESH_OK(),
    )

    const client = createSessionClient(BASE)
    const { response } = await client.POST('/roadmaps', { body })

    expect(response.status).toBe(201)
    expect(receivedBodies).toEqual([body, body])
    expect(receivedRequests[0]).not.toBe(receivedRequests[1])
  })

  it('replays a consumed PUT body after refresh, including its identity field', async () => {
    const body = { title: 'Retry replace', proposed_id: 'put-retry-id', published_visibility: 'private' as const }
    const receivedBodies: unknown[] = []
    const receivedRequests: Request[] = []
    let requestCount = 0
    server.use(
      http.put('*/roadmaps/:roadmapId', async ({ request }) => {
        receivedRequests.push(request)
        receivedBodies.push(await request.json())
        requestCount += 1
        return requestCount === 1
          ? new HttpResponse(null, { status: 401 })
          : HttpResponse.json({}, { status: 200 })
      }),
      REFRESH_OK(),
    )

    const client = createSessionClient(BASE)
    const { response } = await client.PUT('/roadmaps/{roadmap_id}', {
      params: { path: { roadmap_id: 'put-roadmap' }, header: { 'If-Match': 1 } },
      body,
    })

    expect(response.status).toBe(200)
    expect(receivedBodies).toEqual([body, body])
    expect(receivedRequests[0]).not.toBe(receivedRequests[1])
  })

  it('replays a consumed PATCH body after refresh, including its identity field', async () => {
    const body = {
      operations: [{ op: 'set_suggested_path' as const, path: ['patch-retry-id'] }],
    }
    const receivedBodies: unknown[] = []
    const receivedRequests: Request[] = []
    let requestCount = 0
    server.use(
      http.patch('*/roadmaps/:roadmapId', async ({ request }) => {
        receivedRequests.push(request)
        receivedBodies.push(await request.json())
        requestCount += 1
        return requestCount === 1
          ? new HttpResponse(null, { status: 401 })
          : HttpResponse.json({}, { status: 200 })
      }),
      REFRESH_OK(),
    )

    const client = createSessionClient(BASE)
    const { response } = await client.PATCH('/roadmaps/{roadmap_id}', {
      params: { path: { roadmap_id: 'patch-roadmap' }, header: { 'If-Match': 1 } },
      body,
    })

    expect(response.status).toBe(200)
    expect(receivedBodies).toEqual([body, body])
    expect(receivedRequests[0]).not.toBe(receivedRequests[1])
  })
})

describe('createSessionClient reporting ownership', () => {
  it('reports a retried 5xx once as the final response and never reports the replaced 401', async () => {
    let dashboardCalls = 0
    server.use(
      http.get('*/me/dashboard', () => {
        dashboardCalls += 1
        return dashboardCalls === 1
          ? new HttpResponse(null, { status: 401 })
          : new HttpResponse(null, { status: 503 })
      }),
      REFRESH_OK(),
    )

    const { response } = await createSessionClient(BASE).GET('/me/dashboard')
    await Sentry.flush()

    expect(response.status).toBe(503)
    expect(events).toHaveLength(1)
    expect(events[0].tags?.['api.operation']).toBe('get_dashboard_me_dashboard_get')
    expect(events[0].tags?.['api.failure_kind']).toBe('upstream')
    expect(events[0].level).toBe('error')
    expect(events[0].contexts).toEqual({ report: { method: 'GET', status: 503 } })
  })

  it('emits zero envelopes when the retried request succeeds', async () => {
    let dashboardCalls = 0
    server.use(
      http.get('*/me/dashboard', () => {
        dashboardCalls += 1
        return dashboardCalls === 1
          ? new HttpResponse(null, { status: 401 })
          : HttpResponse.json(mockDashboard)
      }),
      REFRESH_OK(),
    )

    const { response } = await createSessionClient(BASE).GET('/me/dashboard')
    await Sentry.flush()

    expect(response.status).toBe(200)
    expect(events).toHaveLength(0)
  })

  it('reports a rejected raw retry once through the retry hook with the same object', async () => {
    server.use(
      http.get('*/me/dashboard', () => new HttpResponse(null, { status: 401 })),
      REFRESH_OK(),
    )
    const originalFetch = globalThis.fetch
    const retryError = new TypeError('offline')
    let dashboardCalls = 0
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = input instanceof Request ? input.url : String(input)
      if (url.includes('/me/dashboard')) {
        dashboardCalls += 1
        if (dashboardCalls === 2) return Promise.reject(retryError)
      }
      return originalFetch(input, init)
    })

    await expect(createSessionClient(BASE).GET('/me/dashboard')).rejects.toBe(retryError)
    await Sentry.flush()

    expect(events).toHaveLength(1)
    expect(events[0].tags?.['api.operation']).toBe('get_dashboard_me_dashboard_get')
    expect(events[0].tags?.['api.failure_kind']).toBe('network')
    expect(events[0].level).toBe('warning')
    fetchSpy.mockRestore()
  })

  it('reports a refresh-request network rejection once and rethrows it unchanged', async () => {
    server.use(http.get('*/me/dashboard', () => new HttpResponse(null, { status: 401 })))
    const originalFetch = globalThis.fetch
    const refreshError = new TypeError('refresh offline')
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = input instanceof Request ? input.url : String(input)
      if (url.includes('/auth/refresh')) return Promise.reject(refreshError)
      return originalFetch(input, init)
    })

    await expect(createSessionClient(BASE).GET('/me/dashboard')).rejects.toBe(refreshError)
    await Sentry.flush()

    expect(events).toHaveLength(1)
    expect(events[0].tags?.['api.operation']).toBe('refresh_auth_refresh_post')
    expect(events[0].tags?.['api.failure_kind']).toBe('network')
    expect(events[0].level).toBe('warning')
    fetchSpy.mockRestore()
  })
})
