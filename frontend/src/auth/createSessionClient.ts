import createClient, { type Client } from 'openapi-fetch'

import type { paths } from '@/api'

/** Path prefix for the session endpoints, which the refresh middleware skips. */
const AUTH_PREFIX = '/auth/'

/**
 * Build the session-aware API client (section 10 "Data fetching").
 *
 * `credentials: 'include'` sends and stores the session cookie across the
 * SPA/API subdomains (cookie `Domain=.usewren.com`). A response middleware makes
 * refresh transparent: on a 401 to a non-auth request it calls `POST /auth/refresh`
 * once (a shared in-flight promise coalesces concurrent 401s) and, on success,
 * retries the original request with the freshly minted access cookie. Auth
 * endpoints are skipped so a failed refresh cannot recurse.
 */
export function createSessionClient(baseUrl: string): Client<paths> {
  const client = createClient<paths>({ baseUrl, credentials: 'include' })
  let refreshing: Promise<boolean> | null = null

  const refreshOnce = (): Promise<boolean> => {
    refreshing ??= client
      .POST('/auth/refresh')
      .then(({ response }) => response.ok)
      .finally(() => {
        refreshing = null
      })
    return refreshing
  }

  client.use({
    async onResponse({ request, response }) {
      if (response.status !== 401) return undefined
      if (new URL(request.url).pathname.startsWith(AUTH_PREFIX)) return undefined
      const refreshed = await refreshOnce()
      if (!refreshed) return undefined
      // Retry once with the rotated session cookie. Product reads are GET, whose
      // requests carry no consumed body, so replaying the Request is safe.
      return fetch(request)
    },
  })

  return client
}
