import * as Sentry from '@sentry/react'

import {
  operationDomainRegistry,
  operationRegistry,
  type OperationDomain,
  type OperationId,
  type OperationKey,
} from '@/api/operationRegistry.generated'

import { classifyApiFailure, type ApiFailureKind } from './classify'

export const RENDER_OPERATION = 'render.app' as const
const KNOWN_OPERATIONS = new Set<string>([...Object.values(operationRegistry), RENDER_OPERATION])
const KNOWN_DOMAINS = new Set<string>(Object.values(operationDomainRegistry))
const KNOWN_KINDS = new Set<string>(['validation', 'upstream', 'network', 'internal'])

export type ReportingOperation = OperationId | typeof RENDER_OPERATION
export type BrowserDomain = OperationDomain
export type BrowserFailureKind = ApiFailureKind | 'internal'

export function isKnownReportingOperation(operationId: string): operationId is ReportingOperation {
  return KNOWN_OPERATIONS.has(operationId)
}

export function isKnownBrowserDomain(value: unknown): value is BrowserDomain {
  return typeof value === 'string' && KNOWN_DOMAINS.has(value)
}

export function isKnownBrowserFailureKind(value: unknown): value is BrowserFailureKind {
  return typeof value === 'string' && KNOWN_KINDS.has(value)
}

export interface ApiFailureReport {
  error?: unknown
  status: number | null
  operationId: ReportingOperation | string
  method: string
  schemaPath: string
  url: string
  domain?: BrowserDomain | string
  kind?: BrowserFailureKind | string
}

function toError(value: unknown): Error {
  if (value instanceof Error) return value
  if (typeof value === 'string') return new Error(value)
  return new Error('API request failed')
}

function operationKeyFor(report: ApiFailureReport): OperationKey | null {
  if (typeof report.method !== 'string' || typeof report.schemaPath !== 'string') return null
  const key = `${report.method} ${report.schemaPath}`
  return Object.prototype.hasOwnProperty.call(operationRegistry, key) ? (key as OperationKey) : null
}

function expectedOperationKey(operationId: string): OperationKey | null {
  for (const [key, registeredOperationId] of Object.entries(operationRegistry)) {
    if (registeredOperationId === operationId) return key as OperationKey
  }
  return null
}

function invalidMetadataFields(report: ApiFailureReport, kind: ApiFailureKind): string[] {
  const fields: string[] = []
  const operationIsKnown = typeof report.operationId === 'string' && isKnownReportingOperation(report.operationId)
  if (!operationIsKnown) fields.push('operationId')
  if (typeof report.method !== 'string' || !/^[A-Z]+$/.test(report.method)) fields.push('method')
  if (typeof report.schemaPath !== 'string' || !report.schemaPath.startsWith('/')) fields.push('schemaPath')

  const expectedKey = operationIsKnown ? expectedOperationKey(report.operationId) : null
  if (expectedKey) {
    const [expectedMethod, ...expectedPath] = expectedKey.split(' ')
    if (report.method !== expectedMethod) fields.push('method')
    if (report.schemaPath !== expectedPath.join(' ')) fields.push('schemaPath')
  } else if (!operationKeyFor(report)) {
    fields.push('operationId')
  }

  const operationKey = operationKeyFor(report)
  const expectedDomain = operationKey ? operationDomainRegistry[operationKey] : undefined
  if (report.domain !== undefined && (!isKnownBrowserDomain(report.domain) || report.domain !== expectedDomain)) {
    fields.push('domain')
  }
  if (report.kind !== undefined && (!isKnownBrowserFailureKind(report.kind) || report.kind !== kind)) {
    fields.push('kind')
  }
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
  return [...new Set(fields)]
}

export function reportApiFailure(report: ApiFailureReport): ApiFailureKind {
  const kind = classifyApiFailure(report)
  const invalidFields = invalidMetadataFields(report, kind)
  if (invalidFields.length > 0) {
    console.warn('reporting_contract_invalid', { fields: invalidFields })
    return kind
  }
  const operationKey = operationKeyFor(report)
  const domain = operationKey ? operationDomainRegistry[operationKey] : undefined
  Sentry.withScope((scope) => {
    scope.setTag('api.operation', report.operationId)
    scope.setTag('api.method', report.method)
    scope.setTag('api.failure_kind', kind)
    if (domain) scope.setTag('api.domain', domain)
    if (kind === 'validation') scope.setTag('expected', 'true')
    if (kind === 'network') scope.setLevel('warning')
    scope.setExtra('api.status', report.status)
    Sentry.captureException(toError(report.error))
  })
  return kind
}

export function reportException(error: unknown): void {
  Sentry.captureException(toError(error))
}
