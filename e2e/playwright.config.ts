import { defineConfig, devices } from '@playwright/test'

import { FRONTEND_BASE_URL } from './helpers/config'

/**
 * Playwright config for the Wren spine E2E. Local runs default to one worker;
 * `E2E_WORKERS=2` enables shared-stack concurrency while `fullyParallel: false`
 * preserves ordering within each file. `globalSetup` pre-flights stack health
 * before any test runs.
 */
const configuredWorkers = process.env.E2E_WORKERS
  ? Number.parseInt(process.env.E2E_WORKERS, 10)
  : process.env.CI
    ? 2
    : 1
const configuredRetries = process.env.E2E_RETRIES
  ? Number.parseInt(process.env.E2E_RETRIES, 10)
  : process.env.CI
    ? 1
    : 0
if (!Number.isInteger(configuredWorkers) || configuredWorkers < 1) {
  throw new Error('E2E_WORKERS must be a positive integer')
}
if (!Number.isInteger(configuredRetries) || configuredRetries < 0) {
  throw new Error('E2E_RETRIES must be a non-negative integer')
}

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
