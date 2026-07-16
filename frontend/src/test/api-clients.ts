import createClient, { type Client } from 'openapi-fetch'

import type { paths, SessionClient } from '@/api'
import { createSessionClient } from '@/auth/createSessionClient'

import { TEST_API_BASE } from './test-api-base'

/**
 * A public API client whose `paths` are extended with test-only stand-in routes.
 *
 * Some client-boundary tests exercise a route that does not (yet) exist in the
 * generated schema (e.g. a `/widget` probe for `runQuery`). Rather than casting
 * the real client to a fake `Client<TestPaths>` via an `as unknown as` round-trip
 * (which discards the generated `paths` type and stops checking the request), the
 * `Extra` type parameter is intersected into the real `paths`. `createClient`
 * returns a genuine `Client<paths & Extra>`, so `client.GET('/widget')` type-checks
 * with NO cast while every real route stays checked against `schema.d.ts`.
 *
 * Defaults `baseUrl` to {@link TEST_API_BASE}. Mirrors the credential-free public
 * client (`createApiClient`); use {@link makeTestSessionClient} for the
 * session-aware variant.
 */
export function makeTestApiClient<Extra extends {} = {}>(
  baseUrl: string = TEST_API_BASE,
): Client<paths & Extra> {
  return createClient<paths & Extra>({ baseUrl })
}

/**
 * A genuine session-aware client (credentials + 401→refresh→retry middleware)
 * built by the real {@link createSessionClient}, defaulting `baseUrl` to
 * {@link TEST_API_BASE}. Provided for symmetry/reuse; tests that unit-test
 * `createSessionClient` itself must call it directly, not through this helper.
 */
export function makeTestSessionClient(baseUrl: string = TEST_API_BASE): SessionClient {
  return createSessionClient(baseUrl)
}
