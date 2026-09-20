import { BROWSER_FAILURE_KINDS, type BrowserFailureKind, type ParsedEnvelope } from './types.ts'

const MAX_INDEXED_STRING_LENGTH = 200

export class MalformedEnvelopeError extends Error {
  constructor() {
    super('malformed envelope')
    this.name = 'MalformedEnvelopeError'
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseJsonLine(line: string): Record<string, unknown> {
  try {
    const value: unknown = JSON.parse(line)
    if (!isObject(value)) throw new Error('not an object')
    return value
  } catch {
    throw new MalformedEnvelopeError()
  }
}

function boundedString(value: unknown): string | null {
  if (typeof value !== 'string' || value.length === 0 || value.length > MAX_INDEXED_STRING_LENGTH) {
    return null
  }
  return value
}

function failureKind(value: unknown): BrowserFailureKind | null {
  return typeof value === 'string' && BROWSER_FAILURE_KINDS.includes(value as BrowserFailureKind)
    ? (value as BrowserFailureKind)
    : null
}

function eventFields(event: Record<string, unknown>): Omit<ParsedEnvelope, 'status' | 'queryIdentity'> {
  const tags = isObject(event.tags) ? event.tags : {}
  const contexts = isObject(event.contexts) ? event.contexts : {}
  const report = isObject(contexts.report) ? contexts.report : {}
  const reportStatus = report.status
  const responseStatus =
    typeof reportStatus === 'number' &&
    Number.isInteger(reportStatus) &&
    reportStatus >= 0 &&
    reportStatus <= 599
      ? reportStatus
      : null

  return {
    operation: boundedString(tags['api.operation']),
    failureKind: failureKind(tags['api.failure_kind']),
    environment: boundedString(event.environment),
    service: boundedString(tags.service),
    method: boundedString(report.method),
    responseStatus,
  }
}

/** Parse the event item from a Sentry newline-delimited envelope. */
export function parseSentryEnvelope(body: Uint8Array, queryIdentity: string | null = null): ParsedEnvelope {
  let text: string
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(body)
  } catch {
    throw new MalformedEnvelopeError()
  }

  const lines = text.split('\n').map((line) => line.endsWith('\r') ? line.slice(0, -1) : line)
  if (lines.at(-1) === '') lines.pop()
  if (lines.length < 3 || lines.some((line) => line.length === 0)) {
    throw new MalformedEnvelopeError()
  }

  parseJsonLine(lines[0])
  let lineIndex = 1
  let firstEvent: Record<string, unknown> | null = null

  while (lineIndex < lines.length) {
    const itemHeader = parseJsonLine(lines[lineIndex])
    lineIndex += 1
    const itemType = itemHeader.type
    if (typeof itemType !== 'string') throw new MalformedEnvelopeError()

    if (itemType !== 'event') {
      return {
        status: 'unsupported',
        queryIdentity,
        operation: null,
        failureKind: null,
        environment: null,
        service: null,
        method: null,
        responseStatus: null,
      }
    }

    if (lineIndex >= lines.length) throw new MalformedEnvelopeError()
    const event = parseJsonLine(lines[lineIndex])
    lineIndex += 1
    firstEvent ??= event
  }

  if (firstEvent === null) throw new MalformedEnvelopeError()
  return { status: 'valid', queryIdentity, ...eventFields(firstEvent) }
}
