export const BROWSER_FAILURE_KINDS = ['upstream', 'network'] as const
export type BrowserFailureKind = (typeof BROWSER_FAILURE_KINDS)[number]

export const RECORDER_QUERY_IDENTITY_HEADER = 'X-Recorder-Query-Identity'
export const MAX_RECORDER_QUERY_IDENTITY_LENGTH = 120

export function isValidRecorderQueryIdentity(value: unknown): value is string {
  return typeof value === 'string'
    && value.length > 0
    && value.length <= MAX_RECORDER_QUERY_IDENTITY_LENGTH
    && /^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(value)
}

export type EnvelopeParseStatus = 'valid' | 'unsupported'

export interface ParsedEnvelope {
  status: EnvelopeParseStatus
  queryIdentity: string | null
  operation: string | null
  failureKind: BrowserFailureKind | null
  environment: string | null
  service: string | null
  method: string | null
  responseStatus: number | null
}

export interface EnvelopeRecord {
  sequence: number
  receivedAtIso: string
  queryIdentity: string
  rawEnvelopeUtf8: string
  parseStatus: EnvelopeParseStatus
  operation: string | null
  failureKind: BrowserFailureKind | null
  environment: string | null
  service: string | null
  method: string | null
  status: number | null
}

export interface EnvelopeQuery {
  queryIdentity: string
  operation: string
  failureKind: BrowserFailureKind
  receivedAfterIso: string
  limit?: number
}

export interface SanitizedEnvelopeArtifact {
  sequence: number
  receivedAtIso: string
  operation: string
  failureKind: BrowserFailureKind
  environment: string
  service: string
  method: string
  status: number | null
}

export interface RecorderLimits {
  maxEnvelopeBytes: number
  maxStoredBytes: number
  maxQueryResults: number
}

export const DEFAULT_RECORDER_LIMITS: RecorderLimits = {
  maxEnvelopeBytes: 1 * 1024 * 1024,
  maxStoredBytes: 32 * 1024 * 1024,
  maxQueryResults: 20,
}
