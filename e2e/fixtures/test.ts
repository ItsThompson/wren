import { test as base, expect } from '@playwright/test'
import type { APIRequestContext, BrowserContext } from '@playwright/test'

import { API_BASE_URL, FRONTEND_BASE_URL } from '../helpers/config'
import {
  createAttemptIdentityFromTestInfo,
  type TestAttemptIdentity,
} from './attempt-identity'
import { type AccountFactory, createAccountFactory } from './account-fixture'
import { OwnedContextResources, ownClosable, ownDisposable } from './context-owner'

export interface WrenFixtures {
  attemptIdentity: TestAttemptIdentity
  contextOwner: OwnedContextResources
  accountFactory: AccountFactory
  apiContext: APIRequestContext
  browserContext: BrowserContext
}

export const test = base.extend<WrenFixtures>({
  attemptIdentity: async ({ browserName: _browserName }, use, testInfo) => {
    await use(createAttemptIdentityFromTestInfo(testInfo))
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

  accountFactory: async ({ playwright, contextOwner, attemptIdentity }, use) => {
    await use(createAccountFactory(playwright, contextOwner, attemptIdentity))
  },
})

export { expect }
