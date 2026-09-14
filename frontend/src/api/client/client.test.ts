import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { createApiClient } from './client'
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
})
