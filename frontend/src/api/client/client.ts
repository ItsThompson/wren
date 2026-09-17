import createClient, { type Client, type Middleware } from 'openapi-fetch'

import { operationRegistry } from '../operationRegistry.generated'
import type { paths } from '../schema'
import { reportApiFailure } from '@/observability/sentry'

const AUTH_PREFIX = '/auth/'

type RetryOnUnauthorized = () => Promise<boolean>

export interface ApiClientOptions {
  credentials?: RequestCredentials
  retryOnUnauthorized?: RetryOnUnauthorized
}

function operationIdFor(method: string, schemaPath: string): string {
  const key = `${method.toUpperCase()} ${schemaPath}` as keyof typeof operationRegistry
  return operationRegistry[key] ?? key
}

function createApiMiddleware(retryOnUnauthorized?: RetryOnUnauthorized): Middleware {
  return {
    async onResponse({ request, response, schemaPath, options }) {
      const operationId = operationIdFor(request.method, schemaPath)
      if (response.status === 401 && retryOnUnauthorized && !new URL(request.url).pathname.startsWith(AUTH_PREFIX)) {
        const refreshed = await retryOnUnauthorized()
        if (refreshed) {
          try {
            return await options.fetch(request.clone())
          } catch (error) {
            reportApiFailure({
              error,
              status: null,
              operationId,
              method: request.method,
              url: request.url,
            })
          }
        }
      }

      if (response.status >= 500) {
        reportApiFailure({
          status: response.status,
          operationId,
          method: request.method,
          url: request.url,
        })
      }
      return undefined
    },
    onError({ error, request, schemaPath }) {
      reportApiFailure({
        error,
        status: null,
        operationId: operationIdFor(request.method, schemaPath),
        method: request.method,
        url: request.url,
      })
    },
  }
}

export function createApiClient(baseUrl: string, clientOptions: ApiClientOptions = {}): Client<paths> {
  const client = createClient<paths>({
    baseUrl,
    credentials: clientOptions.credentials ?? 'omit',
  })
  client.use(createApiMiddleware(clientOptions.retryOnUnauthorized))
  return client
}

export type ApiClient = Client<paths>
export type SessionClient = Client<paths>
