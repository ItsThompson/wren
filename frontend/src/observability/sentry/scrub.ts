import type { Event } from '@sentry/react'

const REDACTED = '[Redacted]'
const SENSITIVE_KEY = /authorization|cookie|password|secret|token|api[-_]?key|set-cookie/i
const SENSITIVE_QUERY = /code|email|password|secret|state|token/i

function scrubValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(scrubValue)
  if (value === null || typeof value !== 'object') return value

  const scrubbed: Record<string, unknown> = {}
  for (const [key, nestedValue] of Object.entries(value)) {
    scrubbed[key] = SENSITIVE_KEY.test(key) ? REDACTED : scrubValue(nestedValue)
  }
  return scrubbed
}

function scrubUrl(value: string): string {
  try {
    const url = new URL(value, window.location.origin)
    for (const key of url.searchParams.keys()) {
      if (SENSITIVE_QUERY.test(key)) url.searchParams.set(key, REDACTED)
    }
    return url.toString()
  } catch {
    return value
  }
}

function scrubHeaders(value: unknown): Record<string, string> {
  if (value instanceof Headers) value = Object.fromEntries(value.entries())
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return {}

  const scrubbed: Record<string, string> = {}
  for (const [key, headerValue] of Object.entries(value)) {
    scrubbed[key] = SENSITIVE_KEY.test(key) ? REDACTED : String(headerValue)
  }
  return scrubbed
}

function scrubQuery(value: NonNullable<Event['request']>['query_string']): NonNullable<Event['request']>['query_string'] {
  if (value === undefined) return value
  if (typeof value === 'string') {
    const params = new URLSearchParams(value)
    for (const key of params.keys()) {
      if (SENSITIVE_QUERY.test(key)) params.set(key, REDACTED)
    }
    return params.toString()
  }
  if (Array.isArray(value)) {
    return value.map(([key, queryValue]): [string, string] => [
      key,
      SENSITIVE_QUERY.test(key) ? REDACTED : queryValue,
    ])
  }

  const scrubbed: Record<string, string> = {}
  for (const [key, queryValue] of Object.entries(value)) {
    scrubbed[key] = SENSITIVE_QUERY.test(key) ? REDACTED : queryValue
  }
  return scrubbed
}

export function scrubSentryEvent<T extends Event>(event: T): T {
  const request = event.request
  if (request) {
    if (request.url) request.url = scrubUrl(request.url)
    if (request.headers) request.headers = scrubHeaders(request.headers)
    if (request.data) request.data = scrubValue(request.data)
    if (request.query_string) request.query_string = scrubQuery(request.query_string)
  }

  if (event.extra) event.extra = scrubValue(event.extra) as Event['extra']
  if (event.contexts) event.contexts = scrubValue(event.contexts) as Event['contexts']
  if (event.breadcrumbs) {
    event.breadcrumbs = event.breadcrumbs.map((breadcrumb) => scrubValue(breadcrumb) as typeof breadcrumb)
  }
  return event
}
