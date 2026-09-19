import { expect, type Page } from '@playwright/test'

import type { AttemptAccountIdentity } from '../fixtures/attempt-identity'

export type BrowserCredentials = Pick<AttemptAccountIdentity, 'email' | 'password'>

export async function registerAccount(page: Page, account: AttemptAccountIdentity): Promise<void> {
  await page.goto('/auth?mode=register')
  await page.getByLabel('Username').fill(account.username)
  await page.getByLabel('Email').fill(account.email)
  await page.getByLabel('Password').fill(account.password)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
}

export async function completeOnboarding(page: Page): Promise<void> {
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/onboarding$/)
  await expect(page.getByText('Welcome to Wren')).toBeVisible()

  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByText('Connect an agent')).toBeVisible()
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByText('How Wren works')).toBeVisible()
  await page.getByRole('button', { name: 'Get started' }).click()

  await expectDashboard(page)
}

export async function logout(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Open account menu' }).click()
  await page.getByRole('menuitem', { name: 'Log out' }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('link', { name: 'Log in' })).toBeVisible()
}

export async function login(page: Page, account: BrowserCredentials): Promise<void> {
  await page.goto('/auth')
  await page.getByLabel('Email').fill(account.email)
  await page.getByLabel('Password').fill(account.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
}

export async function expectDashboard(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole('heading', { name: /your dashboard/i })).toBeVisible()
}
