import { defineConfig, devices } from '@playwright/test'

import { FRONTEND_BASE_URL } from './helpers/config'

/**
 * Playwright config for the Wren spine E2E (spec section 13). Serial by design:
 * `workers: 1` + `fullyParallel: false` so all tests share one live stack
 * deterministically (gofin discipline). `globalSetup` pre-flights stack health
 * before any test runs.
 */
export default defineConfig({
  testDir: './tests',
  globalSetup: './global-setup.ts',
  workers: 1,
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
