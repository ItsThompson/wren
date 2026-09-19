import { expect, test } from '../fixtures/test'

import { completeOnboarding, login } from '../browser/auth'
import { createPublishableRoadmap } from '../helpers/api'

test.describe('public discovery and learner tracking', () => {
  test('shows only public owner content and starts following through the browser', async ({
    accountFactory,
    browserAccountFactory,
    resourceIdentities,
  }) => {
    const owner = await accountFactory.create('owner')
    const learner = await accountFactory.create('learner')
    const publicIdentity = resourceIdentities.roadmap(0)
    const privateDraftIdentity = resourceIdentities.roadmap(1)
    const privatePublishedIdentity = resourceIdentities.roadmap(2)

    const publicRoadmapId = await createPublishableRoadmap(owner.apiContext, publicIdentity)
    const privateDraftId = await createPublishableRoadmap(owner.apiContext, privateDraftIdentity, {
      publishedVisibility: 'private',
    })
    const privatePublishedId = await createPublishableRoadmap(owner.apiContext, privatePublishedIdentity, {
      publishedVisibility: 'private',
    })

    const ownerBrowser = await browserAccountFactory.create('owner-browser')
    const learnerBrowser = await browserAccountFactory.create('learner-browser')
    await login(ownerBrowser.page, owner)
    await completeOnboarding(ownerBrowser.page)
    await login(learnerBrowser.page, learner)
    await completeOnboarding(learnerBrowser.page)

    await ownerBrowser.page.goto(`/roadmaps/${publicRoadmapId}`)
    await expect(ownerBrowser.page.getByRole('heading', { level: 1, name: publicIdentity.title })).toBeVisible()
    await ownerBrowser.page.getByRole('button', { name: 'Publish' }).click()
    await expect(ownerBrowser.page.getByRole('heading', { level: 1, name: publicIdentity.title })).toBeVisible()
    await expect(ownerBrowser.page.getByText('Public access')).toBeVisible()

    await ownerBrowser.page.goto(`/roadmaps/${privatePublishedId}`)
    await expect(ownerBrowser.page.getByRole('heading', { level: 1, name: privatePublishedIdentity.title })).toBeVisible()
    await ownerBrowser.page.getByRole('button', { name: 'Publish' }).click()
    await expect(ownerBrowser.page.getByRole('heading', { level: 1, name: privatePublishedIdentity.title })).toBeVisible()
    await expect(ownerBrowser.page.getByText('Private access')).toBeVisible()

    await learnerBrowser.page.goto(`/user/${owner.username}`)
    await expect(learnerBrowser.page.getByRole('heading', { level: 1, name: owner.username })).toBeVisible()
    await expect(learnerBrowser.page.getByRole('link', { name: publicIdentity.title })).toBeVisible()
    await expect(learnerBrowser.page.getByRole('link', { name: privateDraftIdentity.title })).toHaveCount(0)
    await expect(learnerBrowser.page.getByRole('link', { name: privatePublishedIdentity.title })).toHaveCount(0)

    await learnerBrowser.page.getByRole('link', { name: publicIdentity.title }).click()
    await expect(learnerBrowser.page).toHaveURL(new RegExp(`/roadmaps/${publicRoadmapId}$`))
    await expect(learnerBrowser.page.getByRole('heading', { level: 1, name: publicIdentity.title })).toBeVisible()
    await learnerBrowser.page.getByRole('checkbox', { name: 'Read it' }).check()
    await expect(learnerBrowser.page.getByRole('checkbox', { name: 'Read it' })).toBeChecked()

    await learnerBrowser.page.goto('/dashboard')
    const followingSection = learnerBrowser.page.getByRole('heading', { name: 'Following' }).locator('..')
    await expect(followingSection.getByRole('link', { name: publicIdentity.title })).toBeVisible()

    await learnerBrowser.page.goto(`/roadmaps/${privateDraftId}`)
    await expect(learnerBrowser.page.getByText('Roadmap not found')).toBeVisible()
    await learnerBrowser.page.goto(`/roadmaps/${privatePublishedId}`)
    await expect(learnerBrowser.page.getByText('Roadmap not found')).toBeVisible()
  })
})
