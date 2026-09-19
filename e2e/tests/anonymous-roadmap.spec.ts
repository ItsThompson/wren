import { expect, test } from '../fixtures/test'

import { API_BASE_URL } from '../helpers/config'

import {
  archiveRoadmap,
  createPublishableRoadmap,
  getRoadmap,
  publishRoadmap,
  setPublishedVisibility,
} from '../helpers/api'

test.describe('anonymous roadmap reading', () => {
  test('reads published and archived content without personal requests', async ({
    accountFactory,
    browserContext,
    roadmapIdentity,
  }) => {
    const owner = (await accountFactory.create('anonymous-owner')).apiContext
    const roadmapId = await createPublishableRoadmap(owner, roadmapIdentity, {
      arrays: ['arrays'],
      hashing: ['hashing'],
    })
    const draftGuest = await accountFactory.createGuest()
    expect((await draftGuest.get(`/roadmaps/${roadmapId}`)).status()).toBe(404)
    await publishRoadmap(owner, roadmapId)
    const expectedDocument = await getRoadmap(owner, roadmapId)

    const page = await browserContext.newPage()
    const apiRequests: { path: string; cookie: string | undefined }[] = []
    page.on('request', (request) => {
      if (!request.url().startsWith(API_BASE_URL)) return
      const url = new URL(request.url())
      apiRequests.push({ path: url.pathname, cookie: request.headers().cookie })
    })

    await page.goto(`/roadmaps/${roadmapId}`)
    await expect(page.getByRole('heading', { level: 1, name: roadmapIdentity.title })).toBeVisible()
    await expect(page.getByRole('heading', { level: 3, name: 'Arrays' })).toBeVisible()
    await expect(page.getByText('arrays', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('hashing', { exact: true }).first()).toBeVisible()
    await expect(page.getByRole('link', { name: 'Guide' })).toHaveAttribute('href', 'https://x.test')
    await expect(page.getByRole('link', { name: 'Vid' })).toHaveAttribute('href', 'https://y.test')
    await expect(page.getByText('Read it')).toBeVisible()
    await expect(page.getByText('Drill it')).toBeVisible()
    await expect(page.getByText('Implement a counter')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Log in to track progress' })).toBeVisible()
    await expect(page.getByText('Fork')).not.toBeVisible()
    expect(expectedDocument).toMatchObject({ status: 'published', published_visibility: 'public' })

    await page.goto(`/roadmaps/${roadmapId}/tree`)
    await expect(page.getByRole('link', { name: /Arrays \(progress unavailable\)/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /Hashing \(progress unavailable\)/ })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Log in to track progress' })).toBeVisible()
    await page.getByRole('link', { name: 'List' }).click()
    await expect(page.getByRole('heading', { level: 3, name: 'Hashing' })).toBeVisible()

    const personalRequests = apiRequests.filter(({ path }) =>
      /\/progress$|\/next$|\/follow$|:publish$|:archive$|\/published-visibility$|\/metadata$|^\/me\//.test(path),
    )
    expect(personalRequests).toEqual([])
    const documentRequests = apiRequests.filter(({ path }) => path === `/roadmaps/${roadmapId}`)
    expect(documentRequests.length).toBeGreaterThan(0)
    expect(apiRequests.every(({ cookie }) => cookie === undefined)).toBe(true)

    await archiveRoadmap(owner, roadmapId)
    await page.reload()
    await expect(page.getByText('Archived', { exact: true })).toBeVisible()
    await expect(page.getByText(/available here for reading/i)).toBeVisible()

    await setPublishedVisibility(owner, roadmapId, 'private')
    await page.reload()
    await expect(page.getByText('Roadmap not found')).toBeVisible()

  })

  test('keeps explicit private publication access owner-only across lifecycle states', async ({
    accountFactory,
    roadmapIdentity,
  }) => {
    const owner = (await accountFactory.create('private-owner')).apiContext
    const guest = await accountFactory.createGuest()
    const roadmapId = await createPublishableRoadmap(owner, roadmapIdentity, {
      publishedVisibility: 'private',
    })

    expect((await getRoadmap(owner, roadmapId)).published_visibility).toBe('private')
    expect((await guest.get(`/roadmaps/${roadmapId}`)).status()).toBe(404)

    await publishRoadmap(owner, roadmapId)
    expect((await guest.get(`/roadmaps/${roadmapId}`)).status()).toBe(404)

    await setPublishedVisibility(owner, roadmapId, 'public')
    expect((await guest.get(`/roadmaps/${roadmapId}`)).status()).toBe(200)

    await archiveRoadmap(owner, roadmapId)
    expect((await guest.get(`/roadmaps/${roadmapId}`)).status()).toBe(200)

    await setPublishedVisibility(owner, roadmapId, 'private')
    expect((await guest.get(`/roadmaps/${roadmapId}`)).status()).toBe(404)

  })
})
