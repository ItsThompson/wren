import createClient, { type Client, type Middleware } from 'openapi-fetch'

import { operationRegistry, type OperationId, type OperationKey } from '../operationRegistry.generated'
import type { paths } from '../schema'
import { reportApiFailure } from '@/observability/sentry'

const AUTH_PREFIX = '/auth/'

export type RetryOnUnauthorized = () => Promise<boolean>

export interface ApiClientOptions {
  credentials?: RequestCredentials
  retryOnUnauthorized?: RetryOnUnauthorized
}

export function operationIdFor(method: string, schemaPath: string): OperationId {
  const key = `${method.toUpperCase()} ${schemaPath}`
  if (!Object.prototype.hasOwnProperty.call(operationRegistry, key)) {
    throw new Error(`Unknown API operation: ${key}`)
  }
  return operationRegistry[key as OperationKey]
}

function reportResponseFailure(response: Response, operationId: OperationId, request: Request): void {
  if (response.status < 500) return

  reportApiFailure({
    status: response.status,
    operationId,
    method: request.method,
    url: request.url,
  })
}

function createApiMiddleware(retryOnUnauthorized?: RetryOnUnauthorized): Middleware {
  return {
    async onResponse({ request, response, schemaPath, options }) {
      const operationId = operationIdFor(request.method, schemaPath)
      if (response.status === 401 && retryOnUnauthorized && !new URL(request.url).pathname.startsWith(AUTH_PREFIX)) {
        const refreshed = await retryOnUnauthorized()
        if (refreshed) {
          try {
            const retriedResponse = await options.fetch(request.clone())
            reportResponseFailure(retriedResponse, operationId, request)
            return retriedResponse
          } catch (error) {
            reportApiFailure({
              error,
              status: null,
              operationId,
              method: request.method,
              url: request.url,
            })
            throw error
          }
        }
      }

      reportResponseFailure(response, operationId, request)
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
