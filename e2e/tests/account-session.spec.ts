import { expect, test } from '../fixtures/test'

import {
  completeOnboarding,
  expectDashboard,
  login,
  logout,
  registerAccount,
} from '../browser/auth'

const SESSION_COOKIE_CONTRACTS = [
  { name: 'wren_session', path: '/' },
  { name: 'wren_refresh', path: '/auth' },
] as const

test.describe('account and session journey', () => {
  test('registers, onboards, logs out, logs in, and reloads through HTTPS session cookies', async ({
    browserAccountFactory,
  }) => {
    const account = await browserAccountFactory.create('human')

    await registerAccount(account.page, account)
    await completeOnboarding(account.page)

    const cookies = await account.context.cookies()
    const sessionCookies = cookies
      .filter((cookie) => SESSION_COOKIE_CONTRACTS.some((contract) => contract.name === cookie.name))
      .map(({ name, domain, path, secure }) => ({ name, domain, path, secure }))
    const expectedSessionCookies = SESSION_COOKIE_CONTRACTS.map((contract) => ({
      ...contract,
      domain: '.wren.test',
      secure: true,
    }))
    expect(sessionCookies.sort((left, right) => left.name.localeCompare(right.name))).toEqual(
      expectedSessionCookies.sort((left, right) => left.name.localeCompare(right.name)),
    )

    await logout(account.page)
    await expect(
      account.page.getByRole('heading', { name: /learn anything, in the right order/i }),
    ).toBeVisible()
    await account.page.reload()
    await account.page.goto('/dashboard')
    await expect(account.page.getByText('Log in to see your roadmaps and everything you follow.')).toBeVisible()

    await login(account.page, account)
    const dashboardResponse = await account.page.goto('/dashboard')
    expect(dashboardResponse?.status()).toBe(200)
    await expectDashboard(account.page)
    await account.page.reload()
    await expectDashboard(account.page)

    const connectionsResponse = await account.page.goto('/settings/connections')
    expect(connectionsResponse?.status()).toBe(200)
    await expect(account.page.getByRole('heading', { name: 'Connected agents' })).toBeVisible()
    await expect(account.page.getByText('No connected agents yet.')).toBeVisible()
  })

  test('anonymous protected views keep login surfaces and make no private requests', async ({
    browserContext,
  }) => {
    const page = await browserContext.newPage()
    const privateRequestPaths: string[] = []
    page.on('request', (request) => {
      const path = new URL(request.url()).pathname
      if (path === '/me/dashboard' || path === '/me/clients') privateRequestPaths.push(path)
    })

    await page.goto('/onboarding')
    await expect(page).toHaveURL(/\/auth$/)

    await page.goto('/dashboard')
    await expect(page.getByText('Log in to see your roadmaps and everything you follow.')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Log in' })).toBeVisible()

    await page.goto('/settings/connections')
    await expect(page.getByText('Log in to view and manage the agents connected to your account.')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Connected agents' })).toBeVisible()

    expect(privateRequestPaths).toEqual([])
  })

  test('separate browser account contexts do not share authenticated sessions', async ({
    browserAccountFactory,
  }) => {
    const firstAccount = await browserAccountFactory.create('first')
    const secondAccount = await browserAccountFactory.create('second')

    await registerAccount(firstAccount.page, firstAccount)
    await completeOnboarding(firstAccount.page)

    await secondAccount.page.goto('/dashboard')
    await expect(secondAccount.page.getByText('Log in to see your roadmaps and everything you follow.')).toBeVisible()
    await expect(firstAccount.page.getByRole('heading', { name: /your dashboard/i })).toBeVisible()
  })
})
