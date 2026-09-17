import type { Event } from '@sentry/react'

const REDACTED = '[Redacted]'
const SENSITIVE_KEY = /authorization|cookie|password|secret|token|api[-_]?key|set-cookie/i

function scrubValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(scrubValue)
  if (value === null || typeof value !== 'object') return value

  const scrubbed: Record<string, unknown> = {}
  for (const [key, nestedValue] of Object.entries(value)) {
    scrubbed[key] = SENSITIVE_KEY.test(key) ? REDACTED : scrubValue(nestedValue)
  }
  return scrubbed
}

export function scrubSentryEvent<T extends Event>(event: T): T {
  for (const field of ['request', 'breadcrumbs', 'extra', 'message', 'logentry'] as const) {
    delete event[field]
  }

  if (event.contexts) {
    const reportContext = event.contexts.report
    event.contexts = reportContext
      ? { report: scrubValue(reportContext) as Record<string, unknown> }
      : {}
  }

  for (const value of event.exception?.values ?? []) {
    value.value = '[Redacted exception]'
    delete value.mechanism
    for (const frame of value.stacktrace?.frames ?? []) delete frame.vars
  }
  return event
}
