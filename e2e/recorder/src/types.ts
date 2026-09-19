export const BROWSER_FAILURE_KINDS = ['upstream', 'network'] as const
export type BrowserFailureKind = (typeof BROWSER_FAILURE_KINDS)[number]

export type EnvelopeParseStatus = 'valid' | 'unsupported'

export interface ParsedEnvelope {
  status: EnvelopeParseStatus
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
