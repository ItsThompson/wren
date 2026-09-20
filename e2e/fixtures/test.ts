import { test as base, expect } from '@playwright/test'
import type { APIRequestContext, BrowserContext } from '@playwright/test'

import { API_BASE_URL, FRONTEND_BASE_URL, RECORDER_CONTROL_TOKEN } from '../helpers/config'
import { installRecorderIngestionIdentity } from '../helpers/recorder-client'
import {
  createAttemptIdentityFromTestInfo,
  createAttemptResourceIdentities,
  type AttemptResourceIdentities,
  type OAuthFixtureIdentity,
  type RecorderFixtureIdentity,
  type RoadmapFixtureIdentity,
  type TestAttemptIdentity,
} from './attempt-identity'
import {
  type AccountFactory,
  type BrowserAccountFactory,
  createAccountFactory,
  createBrowserAccountFactory,
} from './account-fixture'
import { createCallbackListener, type CallbackListener } from './callback-listener'
import { OwnedContextResources, ownClosable, ownDisposable } from './context-owner'
import { createRecorderClient, type RecorderClient } from './recorder-client'
import { createAgentFactory, type AgentFactory } from './agent-fixture'
import {
  InMemorySensitiveValueRegistry,
  persistSensitiveValueSnapshot,
  sensitiveValueSnapshotPath,
  type SensitiveValueRegistry,
} from './sensitive-value-registry'

export interface WrenFixtures {
  attemptIdentity: TestAttemptIdentity
  resourceIdentities: AttemptResourceIdentities
  contextOwner: OwnedContextResources
  accountFactory: AccountFactory
  browserAccountFactory: BrowserAccountFactory
  apiContext: APIRequestContext
  browserContext: BrowserContext
  roadmapIdentity: RoadmapFixtureIdentity
  callbackListener: CallbackListener
  oauthIdentity: OAuthFixtureIdentity
  recorderIdentity: RecorderFixtureIdentity
  recorderClient: RecorderClient
  agentFactory: AgentFactory
  sensitiveValueRegistry: SensitiveValueRegistry
}

export const test = base.extend<WrenFixtures>({
  attemptIdentity: async ({ browserName: _browserName }, use, testInfo) => {
    await use(createAttemptIdentityFromTestInfo(testInfo))
  },

  resourceIdentities: async ({ attemptIdentity }, use) => {
    await use(createAttemptResourceIdentities(attemptIdentity))
  },

  contextOwner: async ({ browserName: _browserName }, use) => {
    const owner = new OwnedContextResources()
    try {
      await use(owner)
    } finally {
      await owner.closeAll()
    }
  },

  apiContext: async ({ playwright, contextOwner }, use) => {
    const apiContext = await playwright.request.newContext({ baseURL: API_BASE_URL })
    ownDisposable(contextOwner, apiContext, 'api-context')
    await use(apiContext)
  },

  context: async ({ browser, contextOptions, contextOwner, recorderIdentity, sensitiveValueRegistry }, use) => {
    const context = await browser.newContext(contextOptions)
    await installRecorderIngestionIdentity(context, recorderIdentity.queryIdentity)
    installSensitiveValueCapture(context, sensitiveValueRegistry)
    ownClosable(contextOwner, context, 'context')
    await use(context)
  },

  browserContext: async ({ browser, contextOwner, recorderIdentity }, use) => {
    const browserContext = await browser.newContext({ baseURL: FRONTEND_BASE_URL })
    await installRecorderIngestionIdentity(browserContext, recorderIdentity.queryIdentity)
    ownClosable(contextOwner, browserContext, 'browser-context')
    await use(browserContext)
  },

  sensitiveValueRegistry: async ({ browserName: _browserName }, use, testInfo) => {
    const registry = new InMemorySensitiveValueRegistry()
    registry.register('control-token', RECORDER_CONTROL_TOKEN)
    try {
      await use(registry)
    } finally {
      const path = sensitiveValueSnapshotPath(testInfo.workerIndex)
      if (path !== null) await persistSensitiveValueSnapshot(registry, path)
    }
  },

  accountFactory: async ({ playwright, contextOwner, attemptIdentity, sensitiveValueRegistry }, use) => {
    await use(createAccountFactory(playwright, contextOwner, attemptIdentity, sensitiveValueRegistry))
  },

  browserAccountFactory: async ({ browser, contextOwner, attemptIdentity, sensitiveValueRegistry, recorderIdentity }, use) => {
    await use(createBrowserAccountFactory(
      browser,
      contextOwner,
      attemptIdentity,
      sensitiveValueRegistry,
      recorderIdentity.queryIdentity,
    ))
  },

  roadmapIdentity: async ({ resourceIdentities }, use) => {
    await use(resourceIdentities.roadmap())
  },

  callbackListener: async ({ attemptIdentity, contextOwner }, use) => {
    await use(await createCallbackListener(attemptIdentity, contextOwner))
  },

  oauthIdentity: async ({ resourceIdentities, callbackListener }, use) => {
    await use(resourceIdentities.oauth(0, callbackListener.callbackUrl))
  },

  recorderIdentity: async ({ resourceIdentities }, use) => {
    await use(resourceIdentities.recorder())
  },

  recorderClient: async ({ playwright, contextOwner, recorderIdentity }, use) => {
    await use(await createRecorderClient(playwright.request, contextOwner, recorderIdentity))
  },

  agentFactory: async ({ attemptIdentity, contextOwner, sensitiveValueRegistry }, use) => {
    await use(createAgentFactory(attemptIdentity, contextOwner, sensitiveValueRegistry))
  },
})

function installSensitiveValueCapture(
  context: Pick<BrowserContext, 'on'>,
  sensitiveValues: SensitiveValueRegistry,
): void {
  context.on('request', (request) => {
    const headers = request.headers()
    const cookie = headers.cookie
    const authorization = headers.authorization
    if (cookie !== undefined) sensitiveValues.register('session-cookie', cookie)
    if (authorization !== undefined) sensitiveValues.register('authorization-header', authorization)
  })
  context.on('response', (response) => {
    const setCookie = response.headers()['set-cookie']
    if (setCookie !== undefined) sensitiveValues.register('session-cookie', setCookie)
  })
}

export { expect }
