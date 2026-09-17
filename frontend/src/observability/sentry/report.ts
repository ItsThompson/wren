import * as Sentry from '@sentry/react'

import { operationRegistry, type OperationId } from '@/api/operationRegistry.generated'

import { classifyApiFailure, type ApiFailureKind } from './classify'

const RENDER_OPERATION = 'render.app' as const
const KNOWN_OPERATIONS = new Set<string>([...Object.values(operationRegistry), RENDER_OPERATION])

export type ReportingOperation = OperationId | typeof RENDER_OPERATION

export function isKnownReportingOperation(operationId: string): operationId is ReportingOperation {
  return KNOWN_OPERATIONS.has(operationId)
}

export interface ApiFailureReport {
  error?: unknown
  status: number | null
  operationId: ReportingOperation
  method: string
  url: string
}

function toError(value: unknown): Error {
  if (value instanceof Error) return value
  if (typeof value === 'string') return new Error(value)
  return new Error('API request failed')
}

export function reportApiFailure(report: ApiFailureReport): ApiFailureKind {
  if (!isKnownReportingOperation(report.operationId)) {
    throw new Error(`Unknown reporting operation: ${report.operationId}`)
  }

  const kind = classifyApiFailure(report)
  Sentry.withScope((scope) => {
    scope.setTag('api.operation', report.operationId)
    scope.setTag('api.method', report.method)
    scope.setTag('api.failure_kind', kind)
    if (kind === 'expected') scope.setTag('expected', 'true')
    if (kind === 'network') scope.setLevel('warning')
    scope.setExtra('api.status', report.status)
    Sentry.captureException(toError(report.error))
  })
  return kind
}

export function reportException(error: unknown): void {
  Sentry.captureException(toError(error))
}
