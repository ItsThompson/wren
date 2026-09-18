import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * Load `e2e/.env.test` (plain `KEY=VALUE`, no quotes/export) into `process.env`
 * if present, without a dotenv dependency. Existing environment values win so
 * CI and ad-hoc overrides are respected.
 */
function loadEnvTest(): void {
  const here = dirname(fileURLToPath(import.meta.url))
  const envPath = resolve(here, '..', '.env.test')
  if (!existsSync(envPath)) return
  for (const line of readFileSync(envPath, 'utf8').split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const separator = trimmed.indexOf('=')
    if (separator === -1) continue
    const key = trimmed.slice(0, separator).trim()
    const value = trimmed.slice(separator + 1).trim()
    if (!(key in process.env)) process.env[key] = value
  }
}

loadEnvTest()

/** The SPA origin Playwright drives in the browser. */
export const FRONTEND_BASE_URL = readCanonicalPublicUrl(
  'FRONTEND_BASE_URL',
  'https://app.wren.test',
  'app.wren.test',
)

/** The external-app origin the APIRequestContext seeds and reads against. */
export const API_BASE_URL = readCanonicalPublicUrl(
  'API_BASE_URL',
  'https://api.wren.test',
  'api.wren.test',
)

/** The MCP Resource Server origin the mounted transport exposes to agents. */
export const MCP_BASE_URL = readCanonicalPublicUrl(
  'MCP_BASE_URL',
  'https://mcp.wren.test',
  'mcp.wren.test',
)

function readCanonicalPublicUrl(name: string, fallback: string, expectedHostname: string): string {
  const rawValue = process.env[name] ?? fallback
  let parsedUrl: URL
  try {
    parsedUrl = new URL(rawValue)
  } catch {
    throw new Error(`${name} must be the canonical HTTPS origin https://${expectedHostname}`)
  }
  if (
    parsedUrl.protocol !== 'https:' ||
    parsedUrl.hostname !== expectedHostname ||
    parsedUrl.port !== '' ||
    parsedUrl.pathname !== '/' ||
    parsedUrl.search !== '' ||
    parsedUrl.hash !== '' ||
    parsedUrl.username !== '' ||
    parsedUrl.password !== ''
  ) {
    throw new Error(`${name} must be the canonical HTTPS origin https://${expectedHostname}`)
  }
  return parsedUrl.origin
}

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')

/** The isolated CA used by Node's normal TLS validation. */
export const NODE_CA_CERT_PATH = process.env.NODE_EXTRA_CA_CERTS ?? resolve(
  projectRoot,
  'e2e/ingress/certificates/caroot/rootCA.pem',
)

/** The recorder control secret is never included in browser configuration. */
export const RECORDER_CONTROL_TOKEN = process.env.RECORDER_CONTROL_TOKEN ?? readGeneratedToken(projectRoot)

function readGeneratedToken(root: string): string {
  const tokenPath = resolve(root, 'e2e/keys/recorder-control-token')
  if (!existsSync(tokenPath)) return ''
  return readFileSync(tokenPath, 'utf8').trim()
}
