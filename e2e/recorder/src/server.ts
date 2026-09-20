import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http'
import { timingSafeEqual } from 'node:crypto'

import { MalformedEnvelopeError, parseSentryEnvelope } from './envelope-parser.ts'
import { EnvelopeStore, RecorderStorageLimitError, RecorderValidationError } from './envelope-store.ts'
import {
  BROWSER_FAILURE_KINDS,
  DEFAULT_RECORDER_LIMITS,
  isValidRecorderQueryIdentity,
  type RecorderLimits,
} from './types.ts'

const INGESTION_PATH = /^\/_e2e\/sentry\/api\/[1-9][0-9]*\/envelope\/$/

class HttpRequestError extends Error {
  readonly statusCode: number
  readonly errorCode: string

  constructor(statusCode: number, errorCode: string) {
    super(errorCode)
    this.statusCode = statusCode
    this.errorCode = errorCode
  }
}

export interface RecorderServerOptions {
  controlToken: string
  store?: EnvelopeStore
  limits?: Partial<RecorderLimits>
}

export interface RecorderServer {
  server: Server
  store: EnvelopeStore
}

function isAuthorized(request: IncomingMessage, token: string): boolean {
  if (token.length === 0) return false
  const provided = request.headers['x-recorder-token']
  if (typeof provided !== 'string') return false
  const expectedBytes = Buffer.from(token)
  const providedBytes = Buffer.from(provided)
  return expectedBytes.length === providedBytes.length && timingSafeEqual(expectedBytes, providedBytes)
}

function respond(response: ServerResponse, statusCode: number, payload: Record<string, unknown>): void {
  const body = Buffer.from(JSON.stringify(payload) + '\n')
  response.writeHead(statusCode, {
    'Cache-Control': 'no-store',
    'Content-Length': body.byteLength,
    'Content-Type': 'application/json; charset=utf-8',
  })
  response.end(body)
}

function respondError(response: ServerResponse, statusCode: number, errorCode: string): void {
  respond(response, statusCode, { error: errorCode })
}

async function readBody(request: IncomingMessage, maxBytes: number): Promise<Uint8Array> {
  const declaredLength = request.headers['content-length']
  if (typeof declaredLength !== 'string' || !/^\d+$/.test(declaredLength)) {
    request.resume()
    throw new HttpRequestError(400, 'invalid_content_length')
  }
  const contentLength = Number(declaredLength)
  if (!Number.isSafeInteger(contentLength) || contentLength < 1) {
    request.resume()
    throw new HttpRequestError(400, 'invalid_content_length')
  }
  if (contentLength > maxBytes) {
    request.resume()
    throw new HttpRequestError(413, 'envelope_too_large')
  }

  const chunks: Buffer[] = []
  let receivedBytes = 0
  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
    receivedBytes += buffer.byteLength
    if (receivedBytes > maxBytes) throw new HttpRequestError(413, 'envelope_too_large')
    chunks.push(buffer)
  }
  if (receivedBytes !== contentLength) throw new HttpRequestError(400, 'incomplete_envelope')
  return Buffer.concat(chunks)
}

function recorderQueryIdentity(request: IncomingMessage): string | null {
  const value = request.headers['x-recorder-query-identity']
  return isValidRecorderQueryIdentity(value) ? value : null
}

function queryValue(url: URL, ...names: string[]): string | undefined {
  for (const name of names) {
    const value = url.searchParams.get(name)
    if (value !== null) return value
  }
  return undefined
}

function handleControlRequest(
  request: IncomingMessage,
  response: ServerResponse,
  url: URL,
  store: EnvelopeStore,
  controlToken: string,
): void {
  if (!isAuthorized(request, controlToken)) {
    respondError(response, 401, 'unauthorized')
    return
  }
  if (request.method !== 'GET') {
    respondError(response, 405, 'method_not_allowed')
    return
  }

  if (url.pathname === '/_e2e/recorder/ready') {
    respond(response, 200, { ready: true, parser: 'ready', store: 'ready' })
    return
  }
  if (url.pathname === '/_e2e/recorder/envelopes') {
    const queryIdentity = recorderQueryIdentity(request)
    const operation = queryValue(url, 'operation')
    const failureKind = queryValue(url, 'failureKind', 'failure_kind')
    const receivedAfterIso = queryValue(url, 'receivedAfterIso', 'received_after')
    if (
      queryIdentity === null
      || operation === undefined
      || failureKind === undefined
      || receivedAfterIso === undefined
    ) {
      respondError(response, 400, 'invalid_query')
      return
    }
    const parsedFailureKind = BROWSER_FAILURE_KINDS.find((kind) => kind === failureKind)
    if (parsedFailureKind === undefined) {
      respondError(response, 400, 'invalid_query')
      return
    }
    try {
      const records = store.query({
        queryIdentity,
        operation,
        failureKind: parsedFailureKind,
        receivedAfterIso,
      })
      respond(response, 200, { records })
    } catch (error) {
      if (error instanceof RecorderValidationError) {
        respondError(response, 400, 'invalid_query')
        return
      }
      throw error
    }
    return
  }
  if (url.pathname === '/_e2e/recorder/artifacts') {
    respond(response, 200, { records: store.exportArtifacts() })
    return
  }
  respondError(response, 404, 'not_found')
}

async function handleRequest(
  request: IncomingMessage,
  response: ServerResponse,
  store: EnvelopeStore,
  controlToken: string,
  maxEnvelopeBytes: number,
): Promise<void> {
  const url = new URL(request.url ?? '/', 'http://recorder.invalid')
  if (url.pathname.startsWith('/_e2e/recorder/')) {
    handleControlRequest(request, response, url, store, controlToken)
    return
  }

  if (!INGESTION_PATH.test(url.pathname)) {
    respondError(response, 404, 'not_found')
    return
  }
  if (request.method !== 'POST') {
    respondError(response, 405, 'method_not_allowed')
    return
  }

  const queryIdentity = recorderQueryIdentity(request)
  if (queryIdentity === null) {
    request.resume()
    respondError(response, 400, 'invalid_query_identity')
    return
  }

  let body: Uint8Array
  try {
    body = await readBody(request, maxEnvelopeBytes)
    const parsed = parseSentryEnvelope(body, queryIdentity)
    store.append(body, parsed)
    respond(response, 200, { accepted: true })
  } catch (error) {
    if (error instanceof HttpRequestError || error instanceof MalformedEnvelopeError) {
      const statusCode = error instanceof HttpRequestError ? error.statusCode : 400
      const errorCode = error instanceof HttpRequestError ? error.errorCode : 'malformed_envelope'
      respondError(response, statusCode, errorCode)
      return
    }
    if (error instanceof RecorderStorageLimitError) {
      respondError(response, 507, 'recorder_storage_limit')
      return
    }
    throw error
  }
}

export function createRecorderServer(options: RecorderServerOptions): RecorderServer {
  const store = options.store ?? new EnvelopeStore(options.limits)
  const maxEnvelopeBytes =
    options.limits?.maxEnvelopeBytes ?? DEFAULT_RECORDER_LIMITS.maxEnvelopeBytes
  const server = createServer((request, response) => {
    void handleRequest(request, response, store, options.controlToken, maxEnvelopeBytes).catch(() => {
      if (!response.headersSent) respondError(response, 500, 'recorder_failure')
      else response.destroy()
    })
  })
  server.requestTimeout = 10_000
  server.headersTimeout = 5_000
  return { server, store }
}

export function startRecorderServer(options: RecorderServerOptions, port = 8080): RecorderServer {
  const recorder = createRecorderServer(options)
  recorder.server.listen(port, '0.0.0.0')
  return recorder
}

if (process.argv[1]?.endsWith('/server.ts')) {
  startRecorderServer({ controlToken: process.env.RECORDER_CONTROL_TOKEN ?? '' })
}
