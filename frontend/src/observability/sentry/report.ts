import * as Sentry from '@sentry/react'

import { classifyApiFailure, type ApiFailureKind } from './classify'

export interface ApiFailureReport {
  error?: unknown
  status: number | null
  operationId: string
  method: string
  url: string
}

function toError(value: unknown): Error {
  if (value instanceof Error) return value
  if (typeof value === 'string') return new Error(value)
  return new Error('API request failed')
}

export function reportApiFailure(report: ApiFailureReport): ApiFailureKind {
  const kind = classifyApiFailure(report)
  if (kind === 'expected') return kind

  Sentry.withScope((scope) => {
    scope.setTag('api.operation', report.operationId)
    scope.setTag('api.method', report.method)
    scope.setTag('api.failure_kind', kind)
    scope.setExtra('api.status', report.status)
    Sentry.captureException(toError(report.error))
  })
  return kind
}

export function reportException(error: unknown): void {
  Sentry.captureException(toError(error))
}
