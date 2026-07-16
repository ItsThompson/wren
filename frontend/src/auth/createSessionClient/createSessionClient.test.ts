import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { mockDashboard } from '@/mocks/data'

import { createSessionClient } from './createSessionClient'

const BASE = 'https://api.test'

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
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

    // The original 401 is returned; the refresh 401 does not recurse.
    expect(response.status).toBe(401)
    expect(dashboardCalls).toBe(1)
  })
})
