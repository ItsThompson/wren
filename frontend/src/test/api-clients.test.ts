import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, expectTypeOf, it } from 'vitest'

import { makeTestApiClient, makeTestSessionClient } from './api-clients'
import { TEST_API_BASE } from './test-api-base'

/**
 * A stand-in typed path that is not in the generated schema. Merged into the real
 * `paths` via the `Extra` type parameter so `.GET('/widget')` type-checks with no
 * cast (the whole point of `makeTestApiClient`).
 */
interface WidgetPaths {
  '/widget': {
    get: { responses: { 200: { content: { 'application/json': { id: string } } } } }
  }
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('makeTestApiClient', () => {
  it('merges Extra paths into the real paths so a stand-in .GET type-checks and resolves (no cast)', async () => {
    server.use(http.get('*/widget', () => HttpResponse.json({ id: 'w1' })))

    const client = makeTestApiClient<WidgetPaths>()
    const { data, response } = await client.GET('/widget')

    expect(response.status).toBe(200)
    expect(data).toEqual({ id: 'w1' })
    // The Extra body type flows through: `data` is the typed success body, not `unknown`.
    expectTypeOf(data).toEqualTypeOf<{ id: string } | undefined>()
  })

  it('still type-checks real generated routes alongside the Extra path', async () => {
    server.use(http.get('*/users/:handle', () => HttpResponse.json({ handle: 'ada', display_name: 'Ada', roadmaps: [] })))

    const client = makeTestApiClient<WidgetPaths>()
    const { response } = await client.GET('/users/{handle}', { params: { path: { handle: 'ada' } } })

    expect(response.status).toBe(200)
  })

  it('defaults the base URL to TEST_API_BASE', async () => {
    let requestedUrl = ''
    server.use(
      http.get('*/widget', ({ request }) => {
        requestedUrl = request.url
        return HttpResponse.json({ id: 'w1' })
      }),
    )

    await makeTestApiClient<WidgetPaths>().GET('/widget')

    expect(requestedUrl).toBe(`${TEST_API_BASE}/widget`)
  })

  it('binds a caller-supplied base URL', async () => {
    let requestedUrl = ''
    server.use(
      http.get('*/widget', ({ request }) => {
        requestedUrl = request.url
        return HttpResponse.json({ id: 'w1' })
      }),
    )

    await makeTestApiClient<WidgetPaths>('https://other.test').GET('/widget')

    expect(requestedUrl).toBe('https://other.test/widget')
  })
})

describe('makeTestSessionClient', () => {
  it('returns a genuine session client that refreshes once and retries a 401 (real route, no cast)', async () => {
    let dashboardCalls = 0
    let refreshCalls = 0
    server.use(
      http.get('*/me/dashboard', () => {
        dashboardCalls += 1
        return dashboardCalls === 1
          ? new HttpResponse(null, { status: 401 })
          : HttpResponse.json({ roadmaps: [] })
      }),
      http.post('*/auth/refresh', () => {
        refreshCalls += 1
        return HttpResponse.json({ id: 'u', username: 'ada', email: 'a@b.com', created_at: 'x' })
      }),
    )

    const { response } = await makeTestSessionClient().GET('/me/dashboard')

    expect(response.status).toBe(200)
    expect(refreshCalls).toBe(1)
    expect(dashboardCalls).toBe(2)
  })

  it('defaults the base URL to TEST_API_BASE', async () => {
    let requestedUrl = ''
    server.use(
      http.get('*/me/dashboard', ({ request }) => {
        requestedUrl = request.url
        return HttpResponse.json({ roadmaps: [] })
      }),
    )

    await makeTestSessionClient().GET('/me/dashboard')

    expect(requestedUrl).toBe(`${TEST_API_BASE}/me/dashboard`)
  })
})
