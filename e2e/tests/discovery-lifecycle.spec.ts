import { expect, test } from '../fixtures/test'

import { completeOnboarding, login } from '../browser/auth'
import {
  archiveRoadmap,
  deleteRoadmap,
  editRoadmapDetails,
  forkRoadmap,
  publishRoadmap,
  setRoadmapVisibility,
} from '../browser/roadmap'
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
    await ownerBrowser.page.locator('button:visible').filter({ hasText: /^Publish$/ }).click()
    await expect(ownerBrowser.page.getByRole('heading', { level: 1, name: publicIdentity.title })).toBeVisible()
    await expect(ownerBrowser.page.getByText('Public access')).toBeVisible()

    await ownerBrowser.page.goto(`/roadmaps/${privatePublishedId}`)
    await expect(ownerBrowser.page.getByRole('heading', { level: 1, name: privatePublishedIdentity.title })).toBeVisible()
    await ownerBrowser.page.locator('button:visible').filter({ hasText: /^Publish$/ }).click()
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

  test('keeps owner lifecycle state coherent across owner and non-owner browsers', async ({
    accountFactory,
    browserAccountFactory,
    resourceIdentities,
  }) => {
    const owner = await accountFactory.create('lifecycle-owner')
    const learner = await accountFactory.create('lifecycle-learner')
    const sourceIdentity = resourceIdentities.roadmap(0)
    const deletableIdentity = resourceIdentities.roadmap(1)
    const sourceRoadmapId = await createPublishableRoadmap(owner.apiContext, sourceIdentity)
    const deletableRoadmapId = await createPublishableRoadmap(owner.apiContext, deletableIdentity)

    const ownerBrowser = await browserAccountFactory.create('lifecycle-owner-browser')
    const learnerBrowser = await browserAccountFactory.create('lifecycle-learner-browser')
    await login(ownerBrowser.page, owner)
    await completeOnboarding(ownerBrowser.page)
    await login(learnerBrowser.page, learner)
    await completeOnboarding(learnerBrowser.page)

    const editedMetadata = {
      title: `${sourceIdentity.title} edited`,
      description: 'A browser-saved lifecycle roadmap.',
      subjectTags: 'lifecycle, browser',
    }
    await ownerBrowser.page.goto(`/roadmaps/${sourceRoadmapId}`)
    await editRoadmapDetails(ownerBrowser.page, editedMetadata)
    await ownerBrowser.page.reload()
    await expect(ownerBrowser.page.getByRole('heading', { level: 1, name: editedMetadata.title })).toBeVisible()
    await expect(ownerBrowser.page.getByText(editedMetadata.description, { exact: true })).toBeVisible()
    await expect(ownerBrowser.page.getByText('lifecycle', { exact: true })).toBeVisible()
    await expect(ownerBrowser.page.getByText('browser', { exact: true })).toBeVisible()

    await publishRoadmap(ownerBrowser.page)
    await ownerBrowser.page.goto(`/user/${owner.username}`)
    await expect(ownerBrowser.page.getByRole('link', { name: editedMetadata.title })).toBeVisible()

    await ownerBrowser.page.goto(`/roadmaps/${sourceRoadmapId}`)
    await setRoadmapVisibility(ownerBrowser.page, 'private')
    await ownerBrowser.page.reload()
    await expect(ownerBrowser.page.getByText('Private access', { exact: true })).toBeVisible()
    await expect(ownerBrowser.page.getByRole('heading', { level: 1, name: editedMetadata.title })).toBeVisible()
    await expect(ownerBrowser.page.getByText(editedMetadata.description, { exact: true })).toBeVisible()
    await learnerBrowser.page.goto(`/user/${owner.username}`)
    await expect(learnerBrowser.page.getByRole('link', { name: editedMetadata.title, exact: true })).toHaveCount(0)
    await learnerBrowser.page.goto(`/roadmaps/${sourceRoadmapId}`)
    await expect(learnerBrowser.page.getByText('Roadmap not found')).toBeVisible()

    await setRoadmapVisibility(ownerBrowser.page, 'public')
    await ownerBrowser.page.reload()
    await expect(ownerBrowser.page.getByText('Public access', { exact: true })).toBeVisible()
    await ownerBrowser.page.goto(`/user/${owner.username}`)
    await expect(ownerBrowser.page.getByRole('link', { name: editedMetadata.title })).toBeVisible()
    await learnerBrowser.page.goto(`/user/${owner.username}`)
    await learnerBrowser.page.reload()
    const restoredSourceLink = learnerBrowser.page.getByRole('link', { name: editedMetadata.title, exact: true })
    if (await restoredSourceLink.count() > 0) {
      await restoredSourceLink.click()
    } else {
      await learnerBrowser.page.goto(`/roadmaps/${sourceRoadmapId}`)
    }
    await expect(learnerBrowser.page).toHaveURL(new RegExp(`/roadmaps/${sourceRoadmapId}$`))
    await expect(learnerBrowser.page.getByRole('heading', { level: 1, name: editedMetadata.title })).toBeVisible()

    await ownerBrowser.page.goto(`/roadmaps/${sourceRoadmapId}`)
    const forkedRoadmapId = await forkRoadmap(ownerBrowser.page)
    expect(forkedRoadmapId).not.toBe(sourceRoadmapId)
    await expect(ownerBrowser.page.getByRole('button', { name: 'Publish' }).first()).toBeVisible()
    await ownerBrowser.page.goto('/dashboard')
    await expect(ownerBrowser.page.getByRole('heading', { name: 'Yours' }).locator('..')).toContainText(editedMetadata.title)
    await expect(
      ownerBrowser.page.locator(`a[href="/roadmaps/${forkedRoadmapId}"]`).filter({ hasText: editedMetadata.title }),
    ).toBeVisible()

    await ownerBrowser.page.goto(`/roadmaps/${sourceRoadmapId}`)
    await expect(ownerBrowser.page.getByRole('heading', { level: 1, name: editedMetadata.title })).toBeVisible()
    await expect(ownerBrowser.page.getByText(editedMetadata.description, { exact: true })).toBeVisible()
    await expect(ownerBrowser.page.getByText('lifecycle', { exact: true })).toBeVisible()
    await expect(ownerBrowser.page.getByText('browser', { exact: true })).toBeVisible()
    await expect(ownerBrowser.page.getByText('Public access', { exact: true })).toBeVisible()

    await archiveRoadmap(ownerBrowser.page)
    await ownerBrowser.page.goto(`/user/${owner.username}`)
    await expect(ownerBrowser.page.getByRole('link', { name: editedMetadata.title })).toHaveCount(0)
    await ownerBrowser.page.goto(`/roadmaps/${sourceRoadmapId}`)
    await expect(ownerBrowser.page.getByText('Archived', { exact: true })).toBeVisible()
    await expect(ownerBrowser.page.getByText(/hidden from discovery, but you keep it and your progress/i)).toBeVisible()
    await learnerBrowser.page.goto(`/roadmaps/${sourceRoadmapId}`)
    await expect(learnerBrowser.page.getByText('Archived', { exact: true })).toBeVisible()
    await expect(learnerBrowser.page.getByText(/hidden from discovery, but you keep it and your progress/i)).toBeVisible()

    await ownerBrowser.page.goto(`/roadmaps/${deletableRoadmapId}`)
    await expect(ownerBrowser.page.getByRole('heading', { level: 1, name: deletableIdentity.title })).toBeVisible()
    await deleteRoadmap(ownerBrowser.page)
    await ownerBrowser.page.goto('/dashboard')
    await expect(ownerBrowser.page.getByRole('link', { name: deletableIdentity.title })).toHaveCount(0)
  })
})
