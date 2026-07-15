import createClient, { type Client } from 'openapi-fetch'

import type { paths } from './schema'

/**
 * Typed API client.
 *
 * `openapi-fetch` turns the generated OpenAPI `paths` into one typed call per
 * endpoint over a single generic fetch (`client.GET("/roadmaps/{id}", ...)`),
 * so request/response shapes come straight from `just codegen` output and are
 * never hand-written. Each call is independently mockable by URL (see
 * `src/mocks`). Views receive a client built here with the deployment's API
 * base URL; the base is injected rather than read here so this stays testable.
 */
export const createApiClient = (baseUrl: string): Client<paths> =>
  createClient<paths>({ baseUrl })

export type ApiClient = Client<paths>
