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
import {
  assertPrivateEnvelope,
  assertRawEnvelopeDoesNotContain,
} from '../helpers/envelope-privacy'
import { classifySentryRequest } from '../helpers/sentry-network'
import type { BrowserFailureKind, EnvelopeRecord } from '../recorder/src/types'
import type { SensitiveValueRegistry } from '../fixtures/sensitive-value-registry'

const DASHBOARD_OPERATION = 'get_dashboard_me_dashboard_get'
const CLIENTS_OPERATION = 'list_clients_me_clients_get'
const RECORDER_INGESTION_PATH = '/_e2e/sentry/api/1/envelope/'
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

function assertSensitiveValuesRegistered(
  registry: SensitiveValueRegistry,
  account: { username: string; email: string; password: string },
  expectOAuthValues: boolean,
): void {
  const snapshot = registry.snapshot()
  expect(snapshot.username?.includes(account.username)).toBe(true)
  expect(snapshot.email?.includes(account.email)).toBe(true)
  expect(snapshot.password?.includes(account.password)).toBe(true)
  expect((snapshot['session-cookie']?.length ?? 0) > 0).toBe(true)
  if (!expectOAuthValues) return
  expect((snapshot.token?.length ?? 0) > 0).toBe(true)
  expect((snapshot['authorization-code']?.length ?? 0) > 0).toBe(true)
  expect((snapshot['code-verifier']?.length ?? 0) > 0).toBe(true)
}

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
    const classification = classifySentryRequest(request.url(), FRONTEND_BASE_URL, RECORDER_INGESTION_PATH)
    if (classification === 'unexpected-sentry') {
      evidence.sentryOwnedHosts.push(url.hostname)
      return
    }
    if (classification === 'local-ingestion') evidence.sentryRequestPaths.push(url.pathname)
  })
  page.on('response', (response) => {
    const url = new URL(response.url())
    if (url.origin === FRONTEND_BASE_URL && url.pathname === RECORDER_INGESTION_PATH) {
      evidence.sentryResponseStatuses.push(response.status())
    }
  })
  return evidence
}

function assertRecoveryEnvelope(
  record: EnvelopeRecord,
  operation: string,
  failureKind: BrowserFailureKind,
  status: number | null,
  sensitiveValues: SensitiveValueRegistry,
): void {
  const metadata = {
    operation: record.operation,
    failureKind: record.failureKind,
    environment: record.environment,
    service: record.service,
    method: record.method,
    status: record.status,
  }
  expect(metadata).toEqual({
    operation,
    failureKind,
    environment: 'production',
    service: 'wren-web',
    method: 'GET',
    status,
  })
  assertPrivateEnvelope(record, status, sensitiveValues)
}

function expectRecoveryEvidence(
  evidence: RecoveryNetworkEvidence,
  record: EnvelopeRecord,
): void {
  expect(evidence.sentryRequestPaths).toContain(RECORDER_INGESTION_PATH)
  expect(evidence.sentryResponseStatuses).toContain(200)
  expect(evidence.sentryOwnedHosts).toEqual([])
  assertRawEnvelopeDoesNotContain(record, 'https://api.wren.test/me/', 'API URL')
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
    await account.registerSensitiveCookies()
    assertSensitiveValuesRegistered(sensitiveValueRegistry, account, false)

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
    expectRecoveryEvidence(evidence, record)
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
    await account.registerSensitiveCookies()
    assertSensitiveValuesRegistered(sensitiveValueRegistry, account, true)

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
    expectRecoveryEvidence(evidence, record)
  })
})
