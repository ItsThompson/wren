import type { Client } from 'openapi-fetch'

import { createApiClient } from '@/api/client'
import type { paths } from '@/api/schema'

/**
 * Build the session-aware API client. The shared API middleware owns refresh
 * retries, operation metadata, and failure reporting for every request.
 */
export function createSessionClient(baseUrl: string): Client<paths> {
  let client: Client<paths>
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

  client = createApiClient(baseUrl, {
    credentials: 'include',
    retryOnUnauthorized: refreshOnce,
  })
  return client
}
