import * as Sentry from '@sentry/react'

import {
  operationDomainRegistry,
  operationRegistry,
  type OperationDomain,
  type OperationId,
  type OperationKey,
} from '@/api/operationRegistry.generated'

import { classifyApiFailure, isReportableApiFailure, type ApiFailureKind } from './classify'

// UI failures use fixed operations that cannot collide with generated API
// operations or accept route parameters.
export const RENDER_OPERATION = 'render.app' as const
const ROUTE_OPERATION = 'route.app' as const

const API_OPERATION_IDS = new Set<string>(Object.values(operationRegistry))
const KNOWN_DOMAINS = new Set<string>(Object.values(operationDomainRegistry))
const KNOWN_KINDS = new Set<string>(['validation', 'upstream', 'network', 'internal'])

// Optional-tag policy mirrors the shared Python reporter: a closed key set
// with fixed size limits. Unknown, reserved, empty, non-string, or oversized
// values are omitted without logging their values.
const OPTIONAL_TAG_KEYS = new Set(['code'])
const RESERVED_TAG_KEYS = new Set([
  'expected',
  'service',
  'surface',
  'runtime',
  'api.operation',
  'api.method',
  'api.domain',
  'api.failure_kind',
])
const MAX_TAG_KEY_LENGTH = 32
const MAX_TAG_VALUE_LENGTH = 200

export type ReportingOperation = OperationId
export type BrowserDomain = OperationDomain
export type BrowserFailureKind = ApiFailureKind | 'internal'

export function isKnownBrowserDomain(value: unknown): value is BrowserDomain {
  return typeof value === 'string' && KNOWN_DOMAINS.has(value)
}

export function isKnownBrowserFailureKind(value: unknown): value is BrowserFailureKind {
  return typeof value === 'string' && KNOWN_KINDS.has(value)
}

export interface ApiFailureReport {
  error?: unknown
  status: number | null
  operationId: OperationId | string
  method: string
  schemaPath: string
  url: string
  domain?: BrowserDomain | string
  kind?: BrowserFailureKind | string
  tags?: Record<string, string>
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

function sanitizeOptionalTags(tags: Record<string, string> | undefined): Record<string, string> {
  const sanitized: Record<string, string> = {}
  for (const [key, value] of Object.entries(tags ?? {})) {
    if (
      typeof key !== 'string' ||
      !OPTIONAL_TAG_KEYS.has(key) ||
      RESERVED_TAG_KEYS.has(key) ||
      key.length > MAX_TAG_KEY_LENGTH ||
      typeof value !== 'string' ||
      !value ||
      value.length > MAX_TAG_VALUE_LENGTH
    ) {
      continue
    }
    sanitized[key] = value
  }
  return sanitized
}

function invalidMetadataFields(report: ApiFailureReport, kind: ApiFailureKind): string[] {
  const fields: string[] = []
  const operationId = report.operationId
  if (typeof operationId !== 'string' || !API_OPERATION_IDS.has(operationId)) {
    fields.push('operationId')
  }

  const expectedKey =
    typeof operationId === 'string' && API_OPERATION_IDS.has(operationId)
      ? expectedOperationKey(operationId)
      : null
  if (expectedKey === null) {
    fields.push('operationId')
  } else {
    const [expectedMethod, ...expectedPath] = expectedKey.split(' ')
    if (report.method !== expectedMethod) fields.push('method')
    if (report.schemaPath !== expectedPath.join(' ')) fields.push('schemaPath')
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

function captureSafely(capture: () => void): void {
  try {
    capture()
  } catch {
    // Reporting must never replace a response or a promise rejection: emit
    // only this value-free diagnostic and return.
    console.warn('reporting_failed')
  }
}

export function reportApiFailure(report: ApiFailureReport): ApiFailureKind {
  const kind = classifyApiFailure(report)
  if (!isReportableApiFailure(report)) return kind

  const invalidFields = invalidMetadataFields(report, kind)
  if (invalidFields.length > 0) {
    console.warn('reporting_contract_invalid', { fields: invalidFields })
    return kind
  }
  const operationKey = operationKeyFor(report)
  if (operationKey === null) return kind
  const domain = operationDomainRegistry[operationKey]
  const optionalTags = sanitizeOptionalTags(report.tags)

  captureSafely(() => {
    Sentry.withScope((scope) => {
      for (const [key, value] of Object.entries(optionalTags)) {
        scope.setTag(key, value)
      }
      scope.setTag('api.operation', report.operationId)
      scope.setTag('api.method', report.method)
      scope.setTag('api.failure_kind', kind)
      scope.setTag('api.domain', domain)
      if (kind === 'network') scope.setLevel('warning')
      scope.setContext('report', { method: report.method, status: report.status })
      scope.setFingerprint([report.operationId, kind, '{{ default }}'])
      Sentry.captureException(toError(report.error))
    })
  })
  return kind
}

type CaptureScope = Pick<Sentry.Scope, 'setFingerprint' | 'setTag'>

function applyUiCaptureTags(scope: CaptureScope, operation: string): void {
  scope.setTag('api.operation', operation)
  scope.setTag('api.failure_kind', 'internal')
  scope.setFingerprint([operation, 'internal', '{{ default }}'])
}

// Render capture enriches the SDK ErrorBoundary's own capture with the fixed
// render taxonomy. It never routes through the API report helper.
export function applyRenderCaptureTags(scope: CaptureScope): void {
  applyUiCaptureTags(scope, RENDER_OPERATION)
}

export function reportRouteError(error: unknown): void {
  captureSafely(() => {
    Sentry.withScope((scope) => {
      applyUiCaptureTags(scope, ROUTE_OPERATION)
      Sentry.captureException(error)
    })
  })
}
