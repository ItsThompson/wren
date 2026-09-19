import { expect, test } from '../fixtures/test'

import { createPublishableRoadmap, publishRoadmap } from '../helpers/api'

test.describe('roadmap list filters', () => {
  test('supports ANY, ALL, clear, keyboard use, and narrow layouts', async ({
    accountFactory,
    browserContext,
    roadmapIdentity,
  }) => {
    const owner = (await accountFactory.create('filter-owner')).apiContext
    const roadmapId = await createPublishableRoadmap(owner, roadmapIdentity, {
      arrays: ['arrays', 'shared'],
      hashing: ['hashing', 'shared'],
    })
    await publishRoadmap(owner, roadmapId)

    const page = await browserContext.newPage()
    await page.goto(`/roadmaps/${roadmapId}`)
    const initialUrl = page.url()
    expect(new URL(initialUrl).search).toBe('')

    const panel = page.getByRole('group', { name: 'Roadmap filters' })
    const tags = panel.getByRole('group', { name: 'Filter by tag' })
    await expect(panel.getByText('Showing 2 of 2 topics')).toBeVisible()
    await expect(panel.getByRole('button', { name: 'Clear filters' })).toBeDisabled()
    await expect(panel.getByRole('radio', { name: 'ANY' })).toHaveAttribute('aria-checked', 'true')

    const arrays = tags.getByRole('button', { name: 'arrays' })
    const hashing = tags.getByRole('button', { name: 'hashing' })
    await arrays.focus()
    await page.keyboard.press('Space')
    await hashing.click()
    await expect(panel.getByText('Showing 2 of 2 topics')).toBeVisible()
    await expect(arrays).toHaveAttribute('aria-pressed', 'true')
    await expect(hashing).toHaveAttribute('aria-pressed', 'true')
    expect(page.url()).toBe(initialUrl)

    await panel.getByRole('radio', { name: 'ALL' }).click()
    await expect(panel.getByText('Showing 0 of 2 topics')).toBeVisible()
    await expect(page.getByText('No topics match these filters')).toBeVisible()

    const emptyState = page.getByRole('group', { name: 'Filter results' })
    await emptyState.getByRole('button', { name: 'Clear filters' }).click()
    await expect(panel.getByRole('radio', { name: 'ALL' })).toHaveAttribute('aria-checked', 'true')
    await expect(panel.getByText('Showing 2 of 2 topics')).toBeVisible()
    await expect(page.getByRole('heading', { level: 3, name: 'Arrays' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 3, name: 'Hashing' })).toBeVisible()

    await page.getByRole('link', { name: 'Tree' }).click()
    await expect(page.getByRole('link', { name: 'List' })).toBeVisible()
    await expect(page.getByRole('group', { name: 'Roadmap filters' })).not.toBeVisible()
    await page.getByRole('link', { name: 'List' }).click()
    await expect(panel.getByRole('radio', { name: 'ANY' })).toHaveAttribute('aria-checked', 'true')
    await expect(panel.getByRole('radio', { name: 'ALL' })).toHaveAttribute('aria-checked', 'false')
    await expect(arrays).toHaveAttribute('aria-pressed', 'false')
    await expect(hashing).toHaveAttribute('aria-pressed', 'false')
    expect(new URL(page.url()).search).toBe('')

    await page.setViewportSize({ width: 375, height: 800 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)

  })
})
