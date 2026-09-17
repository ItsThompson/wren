import * as Sentry from '@sentry/react'

import { operationRegistry, type OperationId } from '@/api/operationRegistry.generated'

import { classifyApiFailure, type ApiFailureKind } from './classify'

export const RENDER_OPERATION = 'render.app' as const
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

function invalidMetadataFields(report: ApiFailureReport): string[] {
  const fields: string[] = []
  if (!isKnownReportingOperation(report.operationId)) fields.push('operationId')
  if (!/^[A-Z]+$/.test(report.method)) fields.push('method')
  try {
    new URL(report.url)
  } catch {
    fields.push('url')
  }
  if (
    report.status !== null &&
    (!Number.isInteger(report.status) || report.status < 0 || report.status > 599)
  ) {
    fields.push('status')
  }
  return fields
}

export function reportApiFailure(report: ApiFailureReport): ApiFailureKind {
  const kind = classifyApiFailure(report)
  const invalidFields = invalidMetadataFields(report)
  if (invalidFields.length > 0) {
    console.warn('reporting_contract_invalid', { fields: invalidFields })
    return kind
  }
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
