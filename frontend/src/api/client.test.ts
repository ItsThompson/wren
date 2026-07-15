import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'
import type { Client } from 'openapi-fetch'

import { createApiClient } from './client'
import { handlers } from '@/mocks/handlers'
import { mockDashboard } from '@/mocks/data'
import type { MockDashboard } from '@/mocks/types'

/**
 * The generated `paths` now holds the /auth routes, but `/me/dashboard` is a
 * dev-harness mock route not yet in the schema (dashboard lands in Ticket 25),
 * so this test casts the client to a minimal path shape at the boundary to prove
 * the factory wires openapi-fetch: it issues a request to the configured base
 * URL and parses the JSON response. Real product reads are typed from
 * `schema.d.ts` as their endpoints land.
 */
interface TestPaths {
  '/me/dashboard': {
    get: {
      responses: {
        200: { content: { 'application/json': MockDashboard } }
      }
    }
  }
}

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('createApiClient', () => {
  it('issues typed requests against the configured base URL', async () => {
    const client = createApiClient('https://api.test') as unknown as Client<TestPaths>

    const { data, response } = await client.GET('/me/dashboard')

    expect(response.status).toBe(200)
    expect(data).toEqual(mockDashboard)
  })
})
