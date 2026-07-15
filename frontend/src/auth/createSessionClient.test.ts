import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'
import type { Client } from 'openapi-fetch'

import { createSessionClient } from './createSessionClient'

const BASE = 'https://api.test'

/**
 * A stand-in protected path. The generated `paths` only holds /auth routes, so
 * the client is cast to this minimal shape to exercise the refresh middleware
 * against a product-style read.
 */
interface TestPaths {
  '/protected': {
    get: { responses: { 200: { content: { 'application/json': { ok: boolean } } } } }
  }
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function testClient() {
  return createSessionClient(BASE) as unknown as Client<TestPaths>
}

describe('createSessionClient transparent refresh', () => {
  it('refreshes once and retries the original request on a 401', async () => {
    let protectedCalls = 0
    let refreshCalls = 0
    server.use(
      http.get('*/protected', () => {
        protectedCalls += 1
        // Expired session on first hit; the rotated cookie succeeds on retry.
        return protectedCalls === 1
          ? new HttpResponse(null, { status: 401 })
          : HttpResponse.json({ ok: true })
      }),
      http.post('*/auth/refresh', () => {
        refreshCalls += 1
        return HttpResponse.json({ id: 'u', username: 'ada', email: 'a@b.com', created_at: 'x' })
      }),
    )

    const { data, response } = await testClient().GET('/protected')

    expect(response.status).toBe(200)
    expect(data).toEqual({ ok: true })
    expect(refreshCalls).toBe(1)
    expect(protectedCalls).toBe(2)
  })

  it('does not retry when the refresh itself fails', async () => {
    let protectedCalls = 0
    server.use(
      http.get('*/protected', () => {
        protectedCalls += 1
        return new HttpResponse(null, { status: 401 })
      }),
      http.post('*/auth/refresh', () => new HttpResponse(null, { status: 401 })),
    )

    const { response } = await testClient().GET('/protected')

    // The original 401 is returned; the refresh 401 does not recurse.
    expect(response.status).toBe(401)
    expect(protectedCalls).toBe(1)
  })
})
