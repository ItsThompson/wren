import { test as base, expect } from '@playwright/test'
import type { APIRequestContext, BrowserContext } from '@playwright/test'

import { API_BASE_URL, FRONTEND_BASE_URL, RECORDER_CONTROL_TOKEN } from '../helpers/config'
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

  browserContext: async ({ browser, contextOwner }, use) => {
    const browserContext = await browser.newContext({ baseURL: FRONTEND_BASE_URL })
    ownClosable(contextOwner, browserContext, 'browser-context')
    await use(browserContext)
  },

  sensitiveValueRegistry: async ({}, use, testInfo) => {
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

  browserAccountFactory: async ({ browser, contextOwner, attemptIdentity, sensitiveValueRegistry }, use) => {
    await use(createBrowserAccountFactory(browser, contextOwner, attemptIdentity, sensitiveValueRegistry))
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

export { expect }
