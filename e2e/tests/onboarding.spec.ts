import { expect, test } from '@playwright/test'

import { expectRedirectedToOnboarding, registerNewUser } from '../helpers/onboarding'
import type { AuthenticatedUser } from '../helpers/types'
import { uniqueUser } from '../helpers/users'

/**
 * The onboarding capstone over the live stack: register -> gate redirects to
 * onboarding -> step/skip through the wizard -> complete -> land on the dashboard
 * and STAY there on reload. This is the one layer that proves, against the real
 * backend + a real session resume, the behaviors unit tests cannot: the
 * redirect-loop invariant (US-WIZ-07), the skip==submit terminal path
 * (US-WIZ-06), and the structural guard exemptions (US-GUARD-02/03). Each test
 * mints its own unique user in an isolated browser context.
 */
test.describe('onboarding (register -> wizard -> dashboard, no redirect loop)', () => {
  test('a new account is guided through the wizard and completes onto the dashboard', async ({
    page,
  }) => {
    await registerNewUser(page, uniqueUser('onb'))
    await expectRedirectedToOnboarding(page)

    // US-WIZ-01: the wizard is full-screen and chrome-free (no AppShell top bar),
    // opening on Welcome as step 1 of 3.
    await expect(page.getByRole('banner')).toHaveCount(0)
    await expect(page.getByText('Welcome to Wren')).toBeVisible()
    await expect(page.getByText('Step 1 of 3')).toBeVisible()

    // Continue advances step by step; the progress indicator updates each time.
    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByText('Connect an agent')).toBeVisible()
    await expect(page.getByText('Step 2 of 3')).toBeVisible()

    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByText('How Wren works')).toBeVisible()
    await expect(page.getByText('Step 3 of 3')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Get started' })).toBeVisible()

    // Back returns step by step to Welcome; progress tracks the transitions.
    await page.getByRole('button', { name: 'Back' }).click()
    await expect(page.getByText('Connect an agent')).toBeVisible()
    await expect(page.getByText('Step 2 of 3')).toBeVisible()

    await page.getByRole('button', { name: 'Back' }).click()
    await expect(page.getByText('Welcome to Wren')).toBeVisible()
    await expect(page.getByText('Step 1 of 3')).toBeVisible()

    // Forward to the final step and complete from there.
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    await expect(page.getByRole('button', { name: 'Get started' })).toBeVisible()
    await page.getByRole('button', { name: 'Get started' }).click()

    // US-WIZ-07: `applyUser` runs before navigate, so the just-onboarded user
    // lands on the dashboard and the gate does NOT bounce them to /onboarding.
    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByRole('heading', { name: /your dashboard/i })).toBeVisible()
    await expect(page.getByRole('banner')).toBeVisible()

    // The invariant across a real session resume: a reload stays on the dashboard.
    await page.reload()
    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByRole('heading', { name: /your dashboard/i })).toBeVisible()
  })

  test('skipping every step still completes onboarding and lands on the dashboard', async ({
    page,
  }) => {
    await registerNewUser(page, uniqueUser('skip'))
    await expectRedirectedToOnboarding(page)
    await expect(page.getByText('Welcome to Wren')).toBeVisible()

    // US-WIZ-06: Skip is the same terminal path as submit, so skipping from the
    // first step ends onboarding and lands on the dashboard.
    await page.getByRole('button', { name: 'Skip' }).click()
    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByRole('heading', { name: /your dashboard/i })).toBeVisible()

    // A reload stays on the dashboard, and the session resume the SPA runs on
    // load returns the persisted flag as true: proof the skip path completed
    // onboarding on the backend, not just in client state. Observing the SPA's
    // own resume avoids consuming the rotating refresh token from the test.
    const [resume] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes('/auth/refresh') && response.request().method() === 'POST',
      ),
      page.reload(),
    ])
    expect(resume.status()).toBe(200)
    const resumed = (await resume.json()) as AuthenticatedUser
    expect(resumed.has_completed_onboarding).toBe(true)
    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByRole('heading', { name: /your dashboard/i })).toBeVisible()
  })

  test('an onboarded user visiting /onboarding is redirected to the dashboard', async ({ page }) => {
    await registerNewUser(page, uniqueUser('bounce'))
    await expectRedirectedToOnboarding(page)
    await page.getByRole('button', { name: 'Skip' }).click()
    await expect(page).toHaveURL(/\/dashboard$/)

    // US-GUARD-02: the /onboarding route guard bounces an already-onboarded user
    // (flag resolved true on the session resume) straight to the dashboard.
    await page.goto('/onboarding')
    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByRole('heading', { name: /your dashboard/i })).toBeVisible()
  })

  test('an un-onboarded user on /authorize sees consent, not onboarding', async ({ page }) => {
    await registerNewUser(page, uniqueUser('consent'))

    // US-GUARD-03: /authorize is mounted OUTSIDE the OnboardingGate, so an
    // un-onboarded user is never bounced to /onboarding. Without a live
    // auth_request_id the consent surface shows its expired state; the assertion
    // under test is the structural exemption (no redirect), not the full card.
    await page.goto('/authorize')
    await expect(page).toHaveURL(/\/authorize$/)
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page.getByText(/this request expired/i)).toBeVisible()
    await expect(page.getByText('Welcome to Wren')).toHaveCount(0)
  })
})
