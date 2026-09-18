import type { Client, Middleware } from 'openapi-fetch'

import { createApiClient } from '@/api/client'
import { createApiReportingMiddleware } from '@/observability/sentry'
import type { paths } from '@/api/schema'

const AUTH_PREFIX = '/auth/'
const BODY_METHODS = new Set(['POST', 'PUT', 'PATCH'])

/**
 * Build the session-aware API client. The reporting middleware owns response
 * and rejection reporting for every request. This session middleware owns
 * refresh: on a 401 it refreshes once and replays the original request through
 * the reporting controller's retry-rejection hook, so a rejected raw retry is
 * reported exactly once and the same error object propagates unchanged.
 */
export function createSessionClient(baseUrl: string): Client<paths> {
  const reporting = createApiReportingMiddleware()
  const replayableRequests = new WeakMap<Request, Request>()
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

  const sessionRefreshMiddleware: Middleware = {
    onRequest({ request }) {
      if (BODY_METHODS.has(request.method)) replayableRequests.set(request, request.clone())
    },
    async onResponse({ request, response, schemaPath, options }) {
      const retryRequest = replayableRequests.get(request) ?? null
      replayableRequests.delete(request)
      if (response.status !== 401 || new URL(request.url).pathname.startsWith(AUTH_PREFIX)) {
        return undefined
      }
      const refreshed = await refreshOnce()
      if (!refreshed) return undefined
      // The raw retry bypasses openapi-fetch hooks, so it runs through the
      // reporting controller's dedicated hook: one report on rejection, then
      // the same object rethrows. A retried Response returns to the outer
      // reporting middleware, which classifies the final response once.
      return reporting.observeRetryRejection(
        () => options.fetch(retryRequest ?? request.clone()),
        { method: request.method, schemaPath, url: request.url },
      )
    },
  }

  client = createApiClient(baseUrl, {
    credentials: 'include',
    reporting,
    middleware: sessionRefreshMiddleware,
  })
  return client
}
