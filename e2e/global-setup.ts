import {
  API_BASE_URL,
  FRONTEND_BASE_URL,
  MCP_BASE_URL,
  NODE_CA_CERT_PATH,
  RECORDER_CONTROL_TOKEN,
} from './helpers/config'
import {
  isAuthorizationServerMetadata,
  isProtectedResourceMetadata,
} from './helpers/public-contracts'

const MAX_ATTEMPTS = 60
const INTERVAL_MS = 2000
const REQUEST_TIMEOUT_MS = 5000

export type ReadinessFetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

export interface WaitForOptions {
  readonly maxAttempts?: number
  readonly intervalMs?: number
  readonly requestTimeoutMs?: number
  readonly sleep?: (milliseconds: number) => Promise<void>
  readonly now?: () => number
}

export async function fetchWithTimeout(
  url: string,
  init: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
  fetcher: ReadinessFetcher = globalThis.fetch,
): Promise<Response> {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new Error('readiness request timeout must be positive')
  }

  const timeoutSignal = AbortSignal.timeout(timeoutMs)
  const signal = init.signal == null
    ? timeoutSignal
    : AbortSignal.any([init.signal, timeoutSignal])
  return fetcher(url, { ...init, signal })
}

export async function waitFor(
  label: string,
  check: (requestTimeoutMs: number) => Promise<boolean>,
  options: WaitForOptions = {},
): Promise<void> {
  const maxAttempts = options.maxAttempts ?? MAX_ATTEMPTS
  const intervalMs = options.intervalMs ?? INTERVAL_MS
  const requestTimeoutMs = options.requestTimeoutMs ?? REQUEST_TIMEOUT_MS
  const sleep = options.sleep ?? ((milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds)))
  const now = options.now ?? Date.now
  const readinessWindowMs = maxAttempts * intervalMs
  const deadline = now() + readinessWindowMs

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const remainingMs = deadline - now()
    if (remainingMs <= 0) break
    try {
      if (await check(Math.min(requestTimeoutMs, remainingMs))) {
        console.log(`  ${label} ready (attempt ${attempt}/${maxAttempts})`)
        return
      }
    } catch {
      // Stack still starting; retry until the bounded readiness window expires.
    }
    const remainingAfterCheckMs = deadline - now()
    if (remainingAfterCheckMs <= 0) break
    await sleep(Math.min(intervalMs, remainingAfterCheckMs))
  }
  throw new Error(`${label} did not become ready within ${readinessWindowMs / 1000}s`)
}

export async function responseMatches(
  url: string,
  matches: (document: unknown) => boolean,
  fetcher: ReadinessFetcher = globalThis.fetch,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<boolean> {
  const response = await fetchWithTimeout(url, {}, timeoutMs, fetcher)
  if (!response.ok) return false
  try {
    return matches(await response.json())
  } catch {
    return false
  }
}

export default async function globalSetup(): Promise<void> {
  if (!FRONTEND_BASE_URL.startsWith('https://') || !API_BASE_URL.startsWith('https://') || !MCP_BASE_URL.startsWith('https://')) {
    throw new Error('hosts: E2E public URLs must use HTTPS')
  }
  if (!RECORDER_CONTROL_TOKEN) throw new Error('recorder: control token is missing')
  console.log(`E2E pre-flight: checking public HTTPS contracts with CA ${NODE_CA_CERT_PATH}`)
  await waitFor('app-root', async (requestTimeoutMs) => {
    const response = await fetchWithTimeout(`${FRONTEND_BASE_URL}/`, {}, requestTimeoutMs)
    return response.ok && (await response.text()).includes('id="root"')
  })
  await waitFor('as-metadata', (requestTimeoutMs) =>
    responseMatches(
      `${API_BASE_URL}/.well-known/oauth-authorization-server`,
      (document) => isAuthorizationServerMetadata(document, API_BASE_URL),
      globalThis.fetch,
      requestTimeoutMs,
    ),
  )
  await waitFor('mcp-prm', (requestTimeoutMs) =>
    responseMatches(
      `${MCP_BASE_URL}/.well-known/oauth-protected-resource`,
      (document) =>
        isProtectedResourceMetadata(document, MCP_BASE_URL, API_BASE_URL),
      globalThis.fetch,
      requestTimeoutMs,
    ),
  )
  await waitFor('recorder', async (requestTimeoutMs) => {
    const response = await fetchWithTimeout(`${FRONTEND_BASE_URL}/_e2e/recorder/ready`, {
      headers: { 'X-Recorder-Token': RECORDER_CONTROL_TOKEN },
    }, requestTimeoutMs)
    return response.ok && (await response.text()).includes('"ready":true')
  })
}
