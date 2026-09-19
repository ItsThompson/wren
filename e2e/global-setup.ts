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

async function waitFor(label: string, check: () => Promise<boolean>): Promise<void> {
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    try {
      if (await check()) {
        console.log(`  ${label} ready (attempt ${attempt}/${MAX_ATTEMPTS})`)
        return
      }
    } catch {
      // Stack still starting; retry until the bounded readiness window expires.
    }
    await new Promise((resolve) => setTimeout(resolve, INTERVAL_MS))
  }
  const waited = (MAX_ATTEMPTS * INTERVAL_MS) / 1000
  throw new Error(`${label} did not become ready within ${waited}s`)
}

async function responseMatches(url: string, matches: (document: unknown) => boolean): Promise<boolean> {
  const response = await fetch(url)
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
  await waitFor('app-root', async () => {
    const response = await fetch(`${FRONTEND_BASE_URL}/`)
    return response.ok && (await response.text()).includes('id="root"')
  })
  await waitFor('as-metadata', () =>
    responseMatches(
      `${API_BASE_URL}/.well-known/oauth-authorization-server`,
      (document) => isAuthorizationServerMetadata(document, API_BASE_URL),
    ),
  )
  await waitFor('mcp-prm', () =>
    responseMatches(
      `${MCP_BASE_URL}/.well-known/oauth-protected-resource`,
      (document) =>
        isProtectedResourceMetadata(document, MCP_BASE_URL, API_BASE_URL),
    ),
  )
  await waitFor('recorder', async () => {
    const response = await fetch(`${FRONTEND_BASE_URL}/_e2e/recorder/ready`, {
      headers: { 'X-Recorder-Token': RECORDER_CONTROL_TOKEN },
    })
    return response.ok && (await response.text()).includes('"ready":true')
  })
}
