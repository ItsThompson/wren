import { expect, type Page } from '@playwright/test'

import type { TestUser } from './users'

/**
 * Browser-side onboarding helpers. Unlike the study-spine helpers (which seed
 * and assert through the API), the onboarding capstone must be driven through
 * the real SPA: it proves the redirect-loop invariant and the guard exemptions
 * that only exist in the browser (route guards + `applyUser`-before-navigate +
 * session resume). Each helper drives the live frontend image served by the e2e
 * compose.
 */

/**
 * Register `user` through the real SPA register form. On success the app flips
 * to authenticated and redirects home, so the authenticated top bar (its
 * Dashboard link renders only when signed in) is the settle signal that the
 * session cookie is live in the browser context.
 */
export async function registerNewUser(page: Page, user: TestUser): Promise<void> {
  await page.goto('/auth?mode=register')
  await page.getByLabel('Username').fill(user.username)
  await page.getByLabel('Email').fill(user.email)
  await page.getByLabel('Password').fill(user.password)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('banner').getByRole('link', { name: 'Dashboard' })).toBeVisible()
}

/**
 * Navigate a signed-in, un-onboarded user to a gated in-app route and assert the
 * `OnboardingGate` redirects them to the chrome-free `/onboarding` (US-GUARD-01).
 */
export async function expectRedirectedToOnboarding(page: Page): Promise<void> {
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/onboarding$/)
}
