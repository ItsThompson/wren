import { FRONTEND_BASE_URL, RECORDER_CONTROL_TOKEN } from './config'
import type { BrowserContext } from '@playwright/test'
import {
  isValidRecorderQueryIdentity,
  RECORDER_QUERY_IDENTITY_HEADER,
  type BrowserFailureKind,
  type EnvelopeRecord,
} from '../recorder/src/types'

export function createRecorderQueryIdentityHeaders(queryIdentity: string): Record<string, string> {
  if (!isValidRecorderQueryIdentity(queryIdentity)) throw new Error('invalid recorder query identity')
  return { [RECORDER_QUERY_IDENTITY_HEADER]: queryIdentity }
}

export async function installRecorderIngestionIdentity(
  context: Pick<BrowserContext, 'route'>,
  queryIdentity: string,
): Promise<void> {
  const headers = createRecorderQueryIdentityHeaders(queryIdentity)
  await context.route('**/_e2e/sentry/api/**', async (route) => {
    const requestUrl = new URL(route.request().url())
    if (requestUrl.origin !== FRONTEND_BASE_URL) {
      await route.continue()
      return
    }
    await route.continue({ headers: { ...route.request().headers(), ...headers } })
  })
}

export interface RecorderQueryOptions {
  signal?: AbortSignal
}

export interface RecorderQueryClient {
  query(
    operation: string,
    failureKind: BrowserFailureKind,
    receivedAfterIso: string,
    options?: RecorderQueryOptions,
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
    async query(operation, failureKind, receivedAfterIso, queryOptions): Promise<readonly EnvelopeRecord[]> {
      const url = new URL('/_e2e/recorder/envelopes', baseUrl)
      url.searchParams.set('operation', operation)
      url.searchParams.set('failureKind', failureKind)
      url.searchParams.set('receivedAfterIso', receivedAfterIso)
      const response = await fetcher(url.toString(), {
        headers: {
          'X-Recorder-Token': controlToken,
          ...createRecorderQueryIdentityHeaders(queryIdentity),
        },
        signal: queryOptions?.signal,
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
  options: { timeoutMs?: number; pollIntervalMs?: number; requestTimeoutMs?: number } = {},
): Promise<EnvelopeRecord> {
  const timeoutMs = options.timeoutMs ?? 10_000
  const pollIntervalMs = options.pollIntervalMs ?? 100
  const requestTimeoutMs = options.requestTimeoutMs ?? 2_000
  const deadline = Date.now() + timeoutMs
  let observedCount = 0

  while (Date.now() <= deadline) {
    const requestController = new AbortController()
    const requestTimeout = setTimeout(() => requestController.abort(), Math.min(requestTimeoutMs, deadline - Date.now()))
    let records: readonly EnvelopeRecord[]
    try {
      records = await client.query(operation, failureKind, receivedAfterIso, {
        signal: requestController.signal,
      })
    } catch (error: unknown) {
      if (!requestController.signal.aborted) throw error
      if (Date.now() >= deadline) break
      continue
    } finally {
      clearTimeout(requestTimeout)
    }
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
    isPositiveSafeInteger(value.sequence) &&
    isIsoTimestamp(value.receivedAtIso) &&
    isValidRecorderQueryIdentity(value.queryIdentity) &&
    typeof value.rawEnvelopeUtf8 === 'string' &&
    (value.parseStatus === 'valid' || value.parseStatus === 'unsupported') &&
    (value.operation === null || typeof value.operation === 'string') &&
    (value.failureKind === null || value.failureKind === 'upstream' || value.failureKind === 'network') &&
    (value.environment === null || typeof value.environment === 'string') &&
    (value.service === null || typeof value.service === 'string') &&
    (value.method === null || typeof value.method === 'string') &&
    (value.status === null || isHttpStatus(value.status))
  )
}

function isPositiveSafeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

function isHttpStatus(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 599
}

function isIsoTimestamp(value: unknown): value is string {
  if (typeof value !== 'string') return false
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString() === value
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
