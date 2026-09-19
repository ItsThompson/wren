import { expect, test } from '../fixtures/test'
import type { Page } from '@playwright/test'
import { OAuthScope } from '../agent/types'
import { completeOnboarding, expectDashboard, registerAccount } from '../browser/auth'
import { expectConnectedAgent } from '../browser/connections'
import { API_BASE_URL, FRONTEND_BASE_URL } from '../helpers/config'
import {
  createRecorderQueryClient,
  pollForExactlyOneEnvelope,
} from '../helpers/recorder-client'
import type { BrowserFailureKind, EnvelopeRecord } from '../recorder/src/types'
import type { SensitiveValueRegistry } from '../fixtures/sensitive-value-registry'

const DASHBOARD_OPERATION = 'get_dashboard_me_dashboard_get'
const CLIENTS_OPERATION = 'list_clients_me_clients_get'
const RECORDER_INGESTION_PATH = '/_e2e/sentry/api/1/envelope/'
const SENTRY_OWNED_HOST_PATTERN = /(?:^|\.)sentry\.io$/i
const FORBIDDEN_EVENT_KEYS = new Set([
  'request',
  'user',
  'breadcrumbs',
  'extra',
  'extras',
  'url',
  'filename',
  'abs_path',
  'headers',
  'cookies',
  'authorization',
  'body',
  'query',
  'password',
  'access_token',
  'refresh_token',
  'code_verifier',
  'email',
  'username',
])

interface RecoveryFault {
  readonly wasInjected: () => boolean
  release(): Promise<void>
}

interface RecoveryNetworkEvidence {
  readonly sentryRequestPaths: string[]
  readonly sentryResponseStatuses: number[]
  readonly sentryOwnedHosts: string[]
}

const dashboardEndpoint = new URL('/me/dashboard', API_BASE_URL).toString()
const clientsEndpoint = new URL('/me/clients', API_BASE_URL).toString()

async function installRecoveryFault(
  page: Page,
  endpoint: string,
  mode: 'upstream' | 'network',
): Promise<RecoveryFault> {
  let injected = false
  await page.route(endpoint, async (route) => {
    const request = route.request()
    if (request.method() !== 'GET' || request.url() !== endpoint) {
      await route.continue()
      return
    }
    injected = true
    if (mode === 'upstream') {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'temporary upstream failure' }),
      })
      return
    }
    await route.abort('failed')
  })
  return {
    wasInjected: () => injected,
    release: () => page.unroute(endpoint),
  }
}

function observeRecoveryNetwork(page: Page): RecoveryNetworkEvidence {
  const evidence: RecoveryNetworkEvidence = {
    sentryRequestPaths: [],
    sentryResponseStatuses: [],
    sentryOwnedHosts: [],
  }
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (SENTRY_OWNED_HOST_PATTERN.test(url.hostname)) evidence.sentryOwnedHosts.push(url.hostname)
    if (url.origin === FRONTEND_BASE_URL && url.pathname === RECORDER_INGESTION_PATH) {
      evidence.sentryRequestPaths.push(url.pathname)
    }
  })
  page.on('response', (response) => {
    const url = new URL(response.url())
    if (url.origin === FRONTEND_BASE_URL && url.pathname === RECORDER_INGESTION_PATH) {
      evidence.sentryResponseStatuses.push(response.status())
    }
  })
  return evidence
}

function parseEnvelopeEvent(rawEnvelopeUtf8: string): Record<string, unknown> {
  const lines = rawEnvelopeUtf8.trimEnd().split('\n')
  if (lines.length < 3) throw new Error('recorder returned an incomplete envelope')
  const event = JSON.parse(lines[2]) as unknown
  if (event === null || typeof event !== 'object' || Array.isArray(event)) {
    throw new Error('recorder returned a non-object Sentry event')
  }
  return event as Record<string, unknown>
}

function collectObjectKeys(value: unknown, keys: Set<string>): void {
  if (Array.isArray(value)) {
    for (const item of value) collectObjectKeys(item, keys)
    return
  }
  if (value === null || typeof value !== 'object') return
  for (const [key, nested] of Object.entries(value)) {
    keys.add(key.toLowerCase())
    collectObjectKeys(nested, keys)
  }
}

function assertPrivateEnvelope(record: EnvelopeRecord, sensitiveValues: SensitiveValueRegistry): void {
  const event = parseEnvelopeEvent(record.rawEnvelopeUtf8)
  const keys = new Set<string>()
  collectObjectKeys(event, keys)
  for (const key of FORBIDDEN_EVENT_KEYS) expect(keys).not.toContain(key)
  for (const value of sensitiveValues.values()) expect(record.rawEnvelopeUtf8).not.toContain(value)
  expect(record.rawEnvelopeUtf8).not.toMatch(/\bBearer\s+[A-Za-z0-9._~-]+/i)
  expect(record.rawEnvelopeUtf8).not.toMatch(/(?:session|refresh|access)[_-]?token\s*[:=]/i)
  expect(record.rawEnvelopeUtf8).not.toMatch(/https?:\/\//i)
  expect(event.contexts).toEqual({ report: expect.objectContaining({ method: 'GET' }) })
  expect(event).not.toHaveProperty('request')
  expect(event).not.toHaveProperty('user')
  expect(event).not.toHaveProperty('breadcrumbs')
  expect(event).not.toHaveProperty('extra')
}

function assertRecoveryEnvelope(
  record: EnvelopeRecord,
  operation: string,
  failureKind: BrowserFailureKind,
  status: number | null,
  sensitiveValues: SensitiveValueRegistry,
): void {
  expect(record).toMatchObject({
    operation,
    failureKind,
    environment: 'production',
    service: 'wren-web',
    method: 'GET',
    status,
  })
  assertPrivateEnvelope(record, sensitiveValues)
}

async function expectRecoveryEvidence(
  evidence: RecoveryNetworkEvidence,
  record: EnvelopeRecord,
): Promise<void> {
  expect(evidence.sentryRequestPaths).toContain(RECORDER_INGESTION_PATH)
  expect(evidence.sentryResponseStatuses).toContain(200)
  expect(evidence.sentryOwnedHosts).toEqual([])
  expect(record.rawEnvelopeUtf8).not.toContain('https://api.wren.test/me/')
}

test.describe('browser recovery and envelope privacy', () => {
  test('recovers a dashboard HTTP 500 without reloading or losing the session', async ({
    browserAccountFactory,
    recorderIdentity,
    sensitiveValueRegistry,
  }) => {
    const account = await browserAccountFactory.create('recovery-dashboard')
    await registerAccount(account.page, account)
    await completeOnboarding(account.page)

    const evidence = observeRecoveryNetwork(account.page)
    const receivedAfterIso = new Date().toISOString()
    const fault = await installRecoveryFault(account.page, dashboardEndpoint, 'upstream')
    await account.page.goto('/dashboard')
    await expect.poll(fault.wasInjected).toBe(true)
    await expect(account.page.getByText(/couldn.t load your dashboard/i)).toBeVisible()
    await expect(account.page.getByRole('button', { name: 'Try again', exact: true })).toBeVisible()

    let navigationsAfterFault = 0
    const onNavigation = (): void => {
      navigationsAfterFault += 1
    }
    account.page.on('framenavigated', onNavigation)
    await fault.release()
    await account.page.getByRole('button', { name: 'Try again', exact: true }).click()
    await expectDashboard(account.page)
    await expect(account.page.getByRole('button', { name: 'Open account menu' })).toBeVisible()
    account.page.off('framenavigated', onNavigation)
    expect(navigationsAfterFault).toBe(0)

    const recorder = createRecorderQueryClient({ queryIdentity: recorderIdentity.queryIdentity })
    const record = await pollForExactlyOneEnvelope(
      recorder,
      DASHBOARD_OPERATION,
      'upstream',
      receivedAfterIso,
    )
    assertRecoveryEnvelope(record, DASHBOARD_OPERATION, 'upstream', 500, sensitiveValueRegistry)
    await expectRecoveryEvidence(evidence, record)
  })

  test('recovers a connected-agents network abort and keeps the authorized list', async ({
    browserAccountFactory,
    agentFactory,
    recorderIdentity,
    sensitiveValueRegistry,
  }) => {
    const account = await browserAccountFactory.create('recovery-clients')
    await registerAccount(account.page, account)
    await completeOnboarding(account.page)
    const session = await agentFactory.create(account.page, [OAuthScope.ROADMAPS_READ])

    const evidence = observeRecoveryNetwork(account.page)
    const receivedAfterIso = new Date().toISOString()
    const fault = await installRecoveryFault(account.page, clientsEndpoint, 'network')
    await account.page.goto('/settings/connections')
    await expect.poll(fault.wasInjected).toBe(true)
    await expect(account.page.getByText(/couldn.t load your connected agents/i)).toBeVisible()
    await expect(account.page.getByRole('button', { name: 'Try again', exact: true })).toBeVisible()

    let navigationsAfterFault = 0
    const onNavigation = (): void => {
      navigationsAfterFault += 1
    }
    account.page.on('framenavigated', onNavigation)
    await fault.release()
    await account.page.getByRole('button', { name: 'Try again', exact: true }).click()
    await expectConnectedAgent(account.page, session.authorization.clientName)
    await expect(account.page.getByRole('button', { name: 'Open account menu' })).toBeVisible()
    account.page.off('framenavigated', onNavigation)
    expect(navigationsAfterFault).toBe(0)

    const recorder = createRecorderQueryClient({ queryIdentity: recorderIdentity.queryIdentity })
    const record = await pollForExactlyOneEnvelope(
      recorder,
      CLIENTS_OPERATION,
      'network',
      receivedAfterIso,
    )
    assertRecoveryEnvelope(record, CLIENTS_OPERATION, 'network', null, sensitiveValueRegistry)
    await expectRecoveryEvidence(evidence, record)
  })
})
