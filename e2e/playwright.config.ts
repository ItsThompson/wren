import { defineConfig, devices } from '@playwright/test'

import { FRONTEND_BASE_URL } from './helpers/config'

/**
 * Playwright config for the Wren spine E2E. Local runs default to one worker;
 * `E2E_WORKERS=2` enables shared-stack concurrency while `fullyParallel: false`
 * preserves ordering within each file. `globalSetup` pre-flights stack health
 * before any test runs.
 */
export function parseE2EInteger(name: string, rawValue: string | undefined, fallback: number, minimum: number): number {
  if (rawValue === undefined) return fallback
  const requirement = minimum === 0 ? 'non-negative integer' : 'positive integer'
  if (!/^\d+$/.test(rawValue)) throw new Error(`${name} must be a ${requirement}`)
  const value = Number(rawValue)
  if (!Number.isSafeInteger(value) || value < minimum) throw new Error(`${name} must be a ${requirement}`)
  return value
}

const configuredWorkers = parseE2EInteger('E2E_WORKERS', process.env.E2E_WORKERS, process.env.CI ? 2 : 1, 1)
const configuredRetries = parseE2EInteger('E2E_RETRIES', process.env.E2E_RETRIES, process.env.CI ? 1 : 0, 0)

export default defineConfig({
  testDir: './tests',
  globalSetup: './global-setup.ts',
  workers: configuredWorkers,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: configuredRetries,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: FRONTEND_BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
