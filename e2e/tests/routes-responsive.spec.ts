import { expect, test } from '../fixtures/test'

import { completeOnboarding, login } from '../browser/auth'
import {
  createPublishableRoadmap,
  followRoadmap,
  publishRoadmap,
} from '../helpers/api'

test.describe('direct routes and responsive controls', () => {
  test('resolves public and unknown routes directly', async ({
    accountFactory,
    browserContext,
    roadmapIdentity,
  }) => {
    const publicOwner = await accountFactory.create('route-owner')
    const roadmapId = await createPublishableRoadmap(publicOwner.apiContext, roadmapIdentity)
    await publishRoadmap(publicOwner.apiContext, roadmapId)

    const publicPage = await browserContext.newPage()
    const authResponse = await publicPage.goto('/auth')
    expect(authResponse?.status()).toBe(200)
    await expect(publicPage.getByRole('heading', { name: 'Welcome back' })).toBeVisible()

    const roadmapResponse = await publicPage.goto(`/roadmaps/${roadmapId}`)
    expect(roadmapResponse?.status()).toBe(200)
    await expect(publicPage.getByRole('heading', { level: 1, name: roadmapIdentity.title })).toBeVisible()
    await expect(publicPage.getByRole('heading', { level: 3, name: 'Arrays' })).toBeVisible()

    const treeResponse = await publicPage.goto(`/roadmaps/${roadmapId}/tree`)
    expect(treeResponse?.status()).toBe(200)
    await expect(publicPage.getByRole('link', { name: /Arrays/ })).toBeVisible()

    const profileResponse = await publicPage.goto(`/user/${publicOwner.username}`)
    expect(profileResponse?.status()).toBe(200)
    await expect(publicPage.getByText(`@${publicOwner.username}`)).toBeVisible()
    await expect(publicPage.getByRole('heading', { name: roadmapIdentity.title })).toBeVisible()

    const unknownResponse = await publicPage.goto('/route-that-does-not-exist')
    expect(unknownResponse?.status()).toBe(200)
    await expect(publicPage.getByText('This page isn’t here.')).toBeVisible()
    await publicPage.getByRole('link', { name: 'Back to Wren' }).click()
    await expect(publicPage).toHaveURL(/\/$/)
    await expect(
      publicPage.getByRole('heading', { name: /learn anything, in the right order/i }),
    ).toBeVisible()
  })

  test('resolves authenticated routes directly', async ({
    accountFactory,
    browserContext,
  }) => {
    const authenticated = await accountFactory.create('authenticated')
    const authenticatedPage = await browserContext.newPage()
    await login(authenticatedPage, authenticated)
    await completeOnboarding(authenticatedPage)

    const dashboardResponse = await authenticatedPage.goto('/dashboard')
    expect(dashboardResponse?.status()).toBe(200)
    await expect(authenticatedPage.getByRole('heading', { name: 'Your dashboard' })).toBeVisible()

    const connectionsResponse = await authenticatedPage.goto('/settings/connections')
    expect(connectionsResponse?.status()).toBe(200)
    await expect(authenticatedPage.getByRole('heading', { name: 'Connected agents' })).toBeVisible()
  })

  test('keeps direct OAuth consent outside onboarding', async ({
    accountFactory,
    browserContext,
  }) => {
    const pendingConsent = await accountFactory.create('consent')
    const consentPage = await browserContext.newPage()
    await login(consentPage, pendingConsent)
    const consentResponse = await consentPage.goto('/authorize')
    expect(consentResponse?.status()).toBe(200)
    await expect(consentPage).toHaveURL(/\/authorize$/)
    await expect(consentPage.getByRole('alert')).toBeVisible()
    await expect(consentPage.getByText(/this request expired/i)).toBeVisible()
    await expect(consentPage.getByText('Welcome to Wren')).toHaveCount(0)
  })

  test('keeps account and roadmap controls usable at 375 pixels', async ({
    accountFactory,
    browserContext,
    roadmapIdentity,
  }) => {
    const account = await accountFactory.create('responsive-owner')
    const roadmapId = await createPublishableRoadmap(account.apiContext, roadmapIdentity)
    await publishRoadmap(account.apiContext, roadmapId)
    await followRoadmap(account.apiContext, roadmapId)

    const page = await browserContext.newPage()
    await page.setViewportSize({ width: 375, height: 800 })
    await page.goto('/auth')
    await page.getByLabel('Email').fill(account.email)
    await page.getByLabel('Password').fill(account.password)
    await page.getByRole('button', { name: 'Log in' }).click()
    await expect(page.getByRole('button', { name: 'Open account menu' })).toBeVisible()
    await completeOnboarding(page)

    await page.getByRole('button', { name: 'Open account menu' }).click()
    await expect(page.getByRole('menuitem', { name: 'Dashboard' })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: 'Connected agents' })).toBeVisible()

    await page.goto(`/roadmaps/${roadmapId}`)
    await expect(page.getByRole('link', { name: 'Tree' })).toBeVisible()
    await expect(page.getByRole('checkbox').first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.getByRole('checkbox').first().check()
    await expect(page.getByRole('checkbox').first()).toBeChecked()

    await page.getByRole('link', { name: 'Tree' }).click()
    await expect(page.getByRole('link', { name: 'List' })).toBeVisible()
    await expect(page.getByRole('link', { name: /Arrays/ })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })
})
