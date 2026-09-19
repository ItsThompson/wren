import {
  BROWSER_FAILURE_KINDS,
  DEFAULT_RECORDER_LIMITS,
  type BrowserFailureKind,
  type EnvelopeQuery,
  type EnvelopeRecord,
  type ParsedEnvelope,
  type RecorderLimits,
  type SanitizedEnvelopeArtifact,
} from './types.ts'

export class RecorderValidationError extends Error {
  constructor(message = 'invalid recorder query') {
    super(message)
    this.name = 'RecorderValidationError'
  }
}

export class RecorderStorageLimitError extends Error {
  constructor() {
    super('recorder storage limit exceeded')
    this.name = 'RecorderStorageLimitError'
  }
}

function isFailureKind(value: string): value is BrowserFailureKind {
  return BROWSER_FAILURE_KINDS.includes(value as BrowserFailureKind)
}

function parseTime(value: string): number {
  const parsed = Date.parse(value)
  if (!Number.isFinite(parsed) || new Date(parsed).toISOString() !== value) {
    throw new RecorderValidationError()
  }
  return parsed
}

function validateOperation(operation: string): void {
  if (operation.length === 0 || operation.length > 200) throw new RecorderValidationError()
}

function validateQuery(query: EnvelopeQuery, maxQueryResults: number): Required<EnvelopeQuery> {
  validateOperation(query.operation)
  if (!isFailureKind(query.failureKind)) throw new RecorderValidationError()
  parseTime(query.receivedAfterIso)
  const limit = query.limit ?? maxQueryResults
  if (!Number.isInteger(limit) || limit < 1 || limit > maxQueryResults) {
    throw new RecorderValidationError()
  }
  return {
    operation: query.operation,
    failureKind: query.failureKind,
    receivedAfterIso: query.receivedAfterIso,
    limit,
  }
}

export class EnvelopeStore {
  private readonly limits: RecorderLimits
  private readonly records: EnvelopeRecord[] = []
  private storedBytes = 0
  private nextSequence = 1
  private readonly now: () => Date

  constructor(options: Partial<RecorderLimits> = {}, now: () => Date = () => new Date()) {
    this.limits = { ...DEFAULT_RECORDER_LIMITS, ...options }
    this.now = now
  }

  append(body: Uint8Array, parsed: ParsedEnvelope): EnvelopeRecord {
    if (body.byteLength > this.limits.maxEnvelopeBytes) {
      throw new RecorderStorageLimitError()
    }
    if (this.storedBytes + body.byteLength > this.limits.maxStoredBytes) {
      throw new RecorderStorageLimitError()
    }

    const receivedAt = this.now()
    if (Number.isNaN(receivedAt.getTime())) throw new Error('recorder clock is invalid')
    const record: EnvelopeRecord = {
      sequence: this.nextSequence,
      receivedAtIso: receivedAt.toISOString(),
      rawEnvelopeUtf8: new TextDecoder('utf-8', { fatal: true }).decode(new Uint8Array(body)),
      parseStatus: parsed.status,
      operation: parsed.operation,
      failureKind: parsed.failureKind,
      environment: parsed.environment,
      service: parsed.service,
      method: parsed.method,
      status: parsed.responseStatus,
    }
    this.records.push(record)
    this.storedBytes += body.byteLength
    this.nextSequence += 1
    return { ...record }
  }

  query(query: EnvelopeQuery): EnvelopeRecord[] {
    const validated = validateQuery(query, this.limits.maxQueryResults)
    const receivedAfterTime = parseTime(validated.receivedAfterIso)
    return this.records
      .filter(
        (record) =>
          record.parseStatus === 'valid' &&
          record.operation === validated.operation &&
          record.failureKind === validated.failureKind &&
          Date.parse(record.receivedAtIso) > receivedAfterTime,
      )
      .slice(0, validated.limit)
      .map((record) => ({ ...record }))
  }

  exportArtifacts(): SanitizedEnvelopeArtifact[] {
    return this.records.flatMap((record) => {
      if (
        record.parseStatus !== 'valid' ||
        record.operation === null ||
        record.failureKind === null ||
        record.environment === null ||
        record.service === null ||
        record.method === null
      ) {
        return []
      }
      return [{
        sequence: record.sequence,
        receivedAtIso: record.receivedAtIso,
        operation: record.operation,
        failureKind: record.failureKind,
        environment: record.environment,
        service: record.service,
        method: record.method,
        status: record.status,
      }]
    })
  }
}
