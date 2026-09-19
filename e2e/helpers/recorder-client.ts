import { FRONTEND_BASE_URL, RECORDER_CONTROL_TOKEN } from './config'
import type { BrowserFailureKind, EnvelopeRecord } from '../recorder/src/types'

export interface RecorderQueryClient {
  query(
    operation: string,
    failureKind: BrowserFailureKind,
    receivedAfterIso: string,
  ): Promise<readonly EnvelopeRecord[]>
}

export interface RecorderQueryClientOptions {
  baseUrl?: string
  controlToken?: string
  queryIdentity?: string
  fetcher?: (input: string, init?: RequestInit) => Promise<Response>
}

export function createRecorderQueryClient(options: RecorderQueryClientOptions = {}): RecorderQueryClient {
  const fetcher = options.fetcher ?? ((input, init) => fetch(input, init))
  const baseUrl = options.baseUrl ?? FRONTEND_BASE_URL
  const controlToken = options.controlToken ?? RECORDER_CONTROL_TOKEN
  const queryIdentity = options.queryIdentity ?? 'e2e-recorder-query'

  return {
    async query(operation, failureKind, receivedAfterIso): Promise<readonly EnvelopeRecord[]> {
      const url = new URL('/_e2e/recorder/envelopes', baseUrl)
      url.searchParams.set('operation', operation)
      url.searchParams.set('failureKind', failureKind)
      url.searchParams.set('receivedAfterIso', receivedAfterIso)
      const response = await fetcher(url.toString(), {
        headers: {
          'X-Recorder-Token': controlToken,
          'X-Recorder-Query-Identity': queryIdentity,
        },
      })
      if (!response.ok) throw new Error(`recorder query failed with status ${response.status}`)
      return parseRecorderQueryResponse(await response.json())
    },
  }
}

export async function pollForExactlyOneEnvelope(
  client: RecorderQueryClient,
  operation: string,
  failureKind: BrowserFailureKind,
  receivedAfterIso: string,
  options: { timeoutMs?: number; pollIntervalMs?: number } = {},
): Promise<EnvelopeRecord> {
  const timeoutMs = options.timeoutMs ?? 10_000
  const pollIntervalMs = options.pollIntervalMs ?? 100
  const deadline = Date.now() + timeoutMs
  let observedCount = 0

  while (Date.now() <= deadline) {
    const records = await client.query(operation, failureKind, receivedAfterIso)
    observedCount = records.length
    if (records.length > 1) {
      throw new Error(`recorder query returned duplicate ${operation}/${failureKind} envelopes`)
    }
    const [record] = records
    if (record !== undefined) return record
    await new Promise<void>((resolve) => setTimeout(resolve, pollIntervalMs))
  }

  throw new Error(`recorder query timed out for ${operation}/${failureKind}; observed ${observedCount} records`)
}

function parseRecorderQueryResponse(value: unknown): readonly EnvelopeRecord[] {
  if (!isObject(value) || !Array.isArray(value.records)) throw new Error('recorder query returned an invalid response')
  if (!value.records.every(isEnvelopeRecord)) throw new Error('recorder query returned an invalid record')
  return value.records
}

function isEnvelopeRecord(value: unknown): value is EnvelopeRecord {
  if (!isObject(value)) return false
  return (
    typeof value.sequence === 'number' &&
    typeof value.receivedAtIso === 'string' &&
    typeof value.rawEnvelopeUtf8 === 'string' &&
    (value.operation === null || typeof value.operation === 'string') &&
    (value.failureKind === null || value.failureKind === 'upstream' || value.failureKind === 'network') &&
    (value.environment === null || typeof value.environment === 'string') &&
    (value.service === null || typeof value.service === 'string') &&
    (value.method === null || typeof value.method === 'string') &&
    (value.status === null || typeof value.status === 'number')
  )
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
