import createClient, { type Client, type Middleware } from 'openapi-fetch'

import { operationRegistry, type OperationId, type OperationKey } from '../operationRegistry.generated'
import type { paths } from '../schema'
import { reportApiFailure } from '@/observability/sentry'

const AUTH_PREFIX = '/auth/'
const BODY_METHODS = new Set(['POST', 'PUT', 'PATCH'])

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

function reportResponseAttempt(
  response: Response,
  operationId: OperationId,
  schemaPath: string,
  request: Request,
): void {
  reportApiFailure({
    status: response.status,
    operationId,
    method: request.method,
    schemaPath,
    url: request.url,
  })
}

function createApiMiddleware(retryOnUnauthorized?: RetryOnUnauthorized): Middleware {
  const replayableRequests = new WeakMap<Request, Request>()

  return {
    onRequest({ request }) {
      if (BODY_METHODS.has(request.method)) replayableRequests.set(request, request.clone())
    },
    async onResponse({ request, response, schemaPath, options }) {
      let operationId: OperationId
      try {
        operationId = operationIdFor(request.method, schemaPath)
      } catch {
        replayableRequests.delete(request)
        return undefined
      }

      const retryRequest = replayableRequests.get(request)
      replayableRequests.delete(request)
      reportResponseAttempt(response, operationId, schemaPath, request)
      if (response.status === 401 && retryOnUnauthorized && !new URL(request.url).pathname.startsWith(AUTH_PREFIX)) {
        const refreshed = await retryOnUnauthorized()
        if (refreshed) {
          try {
            const retriedResponse = await options.fetch(retryRequest ?? request.clone())
            reportResponseAttempt(retriedResponse, operationId, schemaPath, request)
            return retriedResponse
          } catch (error) {
            reportApiFailure({
              error,
              status: null,
              operationId,
              method: request.method,
              schemaPath,
              url: request.url,
            })
            throw error
          }
        }
      }

      return response
    },
    onError({ error, request, schemaPath }) {
      let operationId: OperationId
      try {
        operationId = operationIdFor(request.method, schemaPath)
      } catch {
        return
      }
      reportApiFailure({
        error,
        status: null,
        operationId,
        method: request.method,
        schemaPath,
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
