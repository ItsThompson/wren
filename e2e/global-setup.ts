import { API_BASE_URL, FRONTEND_BASE_URL } from './helpers/config'

const MAX_ATTEMPTS = 60
const INTERVAL_MS = 2000

async function waitForOk(label: string, url: string): Promise<void> {
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    try {
      const response = await fetch(url)
      if (response.ok) {
        console.log(`  ${label} healthy (attempt ${attempt}/${MAX_ATTEMPTS})`)
        return
      }
    } catch {
      // Stack still starting; swallow and retry.
    }
    await new Promise((resolve) => setTimeout(resolve, INTERVAL_MS))
  }
  const waited = (MAX_ATTEMPTS * INTERVAL_MS) / 1000
  throw new Error(`${label} did not become healthy within ${waited}s at ${url}`)
}

/**
 * Stack health pre-flight: block the suite until the live
 * stack answers, so a slow container start surfaces as a clear setup failure
 * rather than a flaky first test.
 */
export default async function globalSetup(): Promise<void> {
  console.log('E2E pre-flight: waiting for the stack to report healthy...')
  await waitForOk('frontend', `${FRONTEND_BASE_URL}/healthz`)
  await waitForOk('backend', `${API_BASE_URL}/readyz`)
}
