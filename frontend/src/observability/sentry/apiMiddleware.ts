import type { Middleware } from 'openapi-fetch'

import { operationRegistry, type OperationId, type OperationKey } from '@/api/operationRegistry.generated'

import { isReportableApiFailure } from './classify'
import { reportApiFailure } from './report'

/**
 * Resolve the generated OpenAPI operation id for a method/schema-path pair.
 * Throws on unknown pairs so callers cannot invent unbounded identities.
 */
export function operationIdFor(method: string, schemaPath: string): OperationId {
  const key = `${method.toUpperCase()} ${schemaPath}`
  if (!Object.prototype.hasOwnProperty.call(operationRegistry, key)) {
    throw new Error(`Unknown API operation: ${key}`)
  }
  return operationRegistry[key as OperationKey]
}

export interface RetryRejectionMetadata {
  method: string
  schemaPath: string
  url: string
}

export interface ApiReportingController {
  /** The sole owner of API response/rejection reporting. */
  middleware: Middleware
  /** Wrap a raw retry `fetch`: report one network event on rejection and rethrow the same object. */
  observeRetryRejection: <T>(
    attempt: () => Promise<T>,
    metadata: RetryRejectionMetadata,
  ) => Promise<T>
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

/**
 * The one reporting owner for frontend API traffic. Its middleware observes
 * every response attempt and request rejection; session refresh code routes
 * its raw retry through `observeRetryRejection` because a raw `fetch` bypasses
 * openapi-fetch hooks. `runQuery`, SWR callbacks, and views never report.
 */
export function createApiReportingMiddleware(): ApiReportingController {
  const middleware: Middleware = {
    async onResponse({ request, response, schemaPath }) {
      if (!isReportableApiFailure({ status: response.status })) return undefined

      let operationId: OperationId
      try {
        operationId = operationIdFor(request.method, schemaPath)
      } catch {
        console.warn('reporting_contract_invalid', { fields: ['operationId'] })
        return undefined
      }
      reportResponseAttempt(response, operationId, schemaPath, request)
      return undefined
    },
    onError({ error, request, schemaPath }) {
      let operationId: OperationId
      try {
        operationId = operationIdFor(request.method, schemaPath)
      } catch {
        console.warn('reporting_contract_invalid', { fields: ['operationId'] })
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

  const observeRetryRejection = async <T>(
    attempt: () => Promise<T>,
    metadata: RetryRejectionMetadata,
  ): Promise<T> => {
    try {
      return await attempt()
    } catch (error) {
      try {
        reportApiFailure({
          error,
          status: null,
          operationId: operationIdFor(metadata.method, metadata.schemaPath),
          ...metadata,
        })
      } catch {
        console.warn('reporting_contract_invalid', { fields: ['operationId'] })
      }
      throw error
    }
  }

  return { middleware, observeRetryRejection }
}
