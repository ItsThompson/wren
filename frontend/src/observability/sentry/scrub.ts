import type { Event } from '@sentry/react'

// The only context the reporter constructs. beforeSend keeps exactly these
// keys with scalar values and deletes every other context, so a stray caller
// or SDK context cannot persist URL, query, or body data.
const REPORT_CONTEXT_KEYS = ['method', 'status'] as const
const ALLOWED_TAG_KEYS = new Set([
  'service',
  'surface',
  'runtime',
  'api.operation',
  'api.method',
  'api.domain',
  'api.failure_kind',
  'expected',
  'code',
])
const MAX_TAG_KEY_LENGTH = 32
const MAX_TAG_VALUE_LENGTH = 200

function isScalar(value: unknown): value is string | number | boolean | null {
  return (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  )
}

function sanitizeReportContext(report: Record<string, unknown>): Record<string, unknown> {
  const sanitized: Record<string, unknown> = {}
  for (const key of REPORT_CONTEXT_KEYS) {
    if (isScalar(report[key])) sanitized[key] = report[key]
  }
  return sanitized
}

function sanitizeTags(tags: Record<string, unknown>): Record<string, string> {
  const sanitized: Record<string, string> = {}
  for (const [key, value] of Object.entries(tags)) {
    if (
      ALLOWED_TAG_KEYS.has(key) &&
      key.length <= MAX_TAG_KEY_LENGTH &&
      typeof value === 'string' &&
      value.length > 0 &&
      value.length <= MAX_TAG_VALUE_LENGTH
    ) {
      sanitized[key] = value
    }
  }
  return sanitized
}

export function scrubSentryEvent<T extends Event>(event: T): T {
  for (const field of ['request', 'breadcrumbs', 'extra', 'message', 'logentry'] as const) {
    delete event[field]
  }

  if (event.tags) event.tags = sanitizeTags(event.tags)

  if (event.contexts) {
    const report = event.contexts.report
    event.contexts =
      report && typeof report === 'object'
        ? { report: sanitizeReportContext(report as Record<string, unknown>) }
        : {}
  }

  for (const value of event.exception?.values ?? []) {
    value.value = '[Redacted exception]'
    delete value.mechanism
    for (const frame of value.stacktrace?.frames ?? []) delete frame.vars
  }
  return event
}
