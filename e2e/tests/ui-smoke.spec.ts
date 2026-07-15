import { expect, test } from '@playwright/test'

/**
 * SPA smoke against the live stack: proves the built frontend image serves the
 * bundle and client routing resolves on a deep link. Selectors are semantic
 * (title, heading role, input type) to stay resilient as the frontend source
 * evolves; the authenticated UI flows are exercised via the API spine.
 */
test.describe('SPA smoke (frontend image serves the live SPA)', () => {
  test('the landing renders its hero', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/Wren/i)
    await expect(
      page.getByRole('heading', { name: /learn anything, in the right order/i }),
    ).toBeVisible()
  })

  test('the auth route renders a password field on a deep link', async ({ page }) => {
    await page.goto('/auth')
    await expect(page.locator('input[type="password"]')).toBeVisible()
  })
})
