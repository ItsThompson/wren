import type { EnvelopeRecord } from '../recorder/src/types'
import type { SensitiveValueRegistry } from '../fixtures/sensitive-value-registry'

const FORBIDDEN_EVENT_KEYS = new Set([
  'request',
  'user',
  'breadcrumbs',
  'extra',
  'extras',
  'url',
  'filename',
  'abs_path',
  'headers',
  'cookies',
  'authorization',
  'body',
  'query',
  'password',
  'access_token',
  'refresh_token',
  'code_verifier',
  'email',
  'username',
])

export function assertPrivateEnvelope(
  record: EnvelopeRecord,
  status: number | null,
  sensitiveValues: SensitiveValueRegistry,
): void {
  const event = parseEnvelopeEvent(record.rawEnvelopeUtf8)
  const keys = new Set<string>()
  collectObjectKeys(event, keys)
  for (const key of FORBIDDEN_EVENT_KEYS) {
    if (keys.has(key)) throw new Error(`privacy check failed: forbidden event key ${key}`)
  }

  for (const [category, values] of Object.entries(sensitiveValues.snapshot())) {
    if (values?.some((value) => record.rawEnvelopeUtf8.includes(value))) {
      throw new Error(`privacy check failed: registered sensitive value present in ${category}`)
    }
  }
  assertRawEnvelopeDoesNotMatch(record, /\bBearer\s+[A-Za-z0-9._~-]+/i, 'bearer token')
  assertRawEnvelopeDoesNotMatch(record, /(?:session|refresh|access)[_-]?token\s*[:=]/i, 'token field')
  assertRawEnvelopeDoesNotMatch(record, /https?:\/\//i, 'HTTP URL')

  const contexts = getObjectProperty(event, 'contexts')
  const report = contexts === undefined ? undefined : getObjectProperty(contexts, 'report')
  if (report === undefined) throw new Error('privacy check failed: report context missing')
  const reportKeys = Object.keys(report).sort()
  if (reportKeys.join(',') !== 'method,status') {
    throw new Error('privacy check failed: report context shape changed')
  }
  if (report.method !== 'GET' || report.status !== status) {
    throw new Error('privacy check failed: report context values changed')
  }
}

export function assertRawEnvelopeDoesNotContain(record: EnvelopeRecord, value: string, label: string): void {
  if (record.rawEnvelopeUtf8.includes(value)) {
    throw new Error(`privacy check failed: ${label} present`)
  }
}

function assertRawEnvelopeDoesNotMatch(record: EnvelopeRecord, pattern: RegExp, label: string): void {
  if (pattern.test(record.rawEnvelopeUtf8)) {
    throw new Error(`privacy check failed: ${label} present`)
  }
}

function parseEnvelopeEvent(rawEnvelopeUtf8: string): Record<string, unknown> {
  const lines = rawEnvelopeUtf8.trimEnd().split('\n')
  if (lines.length < 3) throw new Error('recorder returned an incomplete envelope')
  const event: unknown = JSON.parse(lines[2])
  if (!isObject(event)) throw new Error('recorder returned a non-object Sentry event')
  return event
}

function collectObjectKeys(value: unknown, keys: Set<string>): void {
  if (Array.isArray(value)) {
    for (const item of value) collectObjectKeys(item, keys)
    return
  }
  if (!isObject(value)) return
  for (const [key, nested] of Object.entries(value)) {
    keys.add(key.toLowerCase())
    collectObjectKeys(nested, keys)
  }
}

function getObjectProperty(value: unknown, property: string): Record<string, unknown> | undefined {
  if (!isObject(value)) return undefined
  const nested = value[property]
  return isObject(nested) ? nested : undefined
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
