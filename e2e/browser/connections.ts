import { expect, type Page } from '@playwright/test'

export async function openConnections(page: Page): Promise<void> {
  await page.goto('/settings/connections')
  await expect(page.getByRole('heading', { name: 'Connected agents', exact: true })).toBeVisible()
}

export async function expectConnectedAgent(page: Page, clientName: string): Promise<void> {
  const row = connectedAgentRow(page, clientName)
  await expect(row).toHaveCount(1)
  await expect(row.getByText(clientName, { exact: true })).toBeVisible()
}

export async function revokeConnectedAgent(page: Page, clientName: string): Promise<void> {
  const row = connectedAgentRow(page, clientName)
  await expect(row).toHaveCount(1)
  await row.getByRole('button', { name: 'Revoke', exact: true }).click()
  await row.getByRole('button', { name: 'Confirm revoke', exact: true }).click()
  await expect(row).toHaveCount(0)
}

function connectedAgentRow(page: Page, clientName: string) {
  return page.getByRole('listitem').filter({ hasText: clientName })
}
