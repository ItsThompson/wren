import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * Load `e2e/.env.test` (plain `KEY=VALUE`, no quotes/export) into `process.env`
 * if present, without a dotenv dependency. A missing file is fine: the defaults
 * below match `e2e/docker-compose.e2e.yml`'s published host ports. Existing
 * environment values win so CI/ad-hoc overrides are respected.
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
export const FRONTEND_BASE_URL = process.env.FRONTEND_BASE_URL ?? 'http://localhost:5173'

/** The external-app origin the APIRequestContext seeds and reads against. */
export const API_BASE_URL = process.env.API_BASE_URL ?? 'http://localhost:8000'
