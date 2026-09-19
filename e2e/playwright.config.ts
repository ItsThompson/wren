import { defineConfig, devices } from '@playwright/test'

import { FRONTEND_BASE_URL } from './helpers/config'

/**
 * Playwright config for the Wren spine E2E. Serial by design:
 * `workers: 1` + `fullyParallel: false` so all tests share one live stack
 * deterministically. `globalSetup` pre-flights stack health
 * before any test runs.
 */
const configuredWorkers = process.env.E2E_WORKERS
  ? Number.parseInt(process.env.E2E_WORKERS, 10)
  : 1
if (!Number.isInteger(configuredWorkers) || configuredWorkers < 1) {
  throw new Error('E2E_WORKERS must be a positive integer')
}

export default defineConfig({
  testDir: './tests',
  globalSetup: './global-setup.ts',
  workers: configuredWorkers,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
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
