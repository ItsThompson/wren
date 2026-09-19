import type {
  APIRequest,
  APIRequestContext,
  Browser,
  BrowserContext,
  Page,
} from '@playwright/test'
import { expect } from '@playwright/test'

import { API_BASE_URL, FRONTEND_BASE_URL } from '../helpers/config'
import {
  createAccountIdentity,
  type AttemptAccountIdentity,
  type TestAttemptIdentity,
} from './attempt-identity'
import { type ContextOwner, ownClosable, ownDisposable } from './context-owner'

export interface TestAccount extends AttemptAccountIdentity {
  apiContext: APIRequestContext
}

export interface BrowserAccount extends AttemptAccountIdentity {
  context: BrowserContext
  page: Page
}

export interface AccountFactory {
  create(role?: string): Promise<TestAccount>
  createGuest(): Promise<APIRequestContext>
}

export interface BrowserAccountFactory {
  create(role?: string): Promise<BrowserAccount>
}

interface PlaywrightRequest {
  request: Pick<APIRequest, 'newContext'>
}

export function createBrowserAccountFactory(
  browser: Pick<Browser, 'newContext'>,
  owner: ContextOwner,
  attemptIdentity: TestAttemptIdentity,
): BrowserAccountFactory {
  let accountIndex = 0

  return {
    async create(role = 'human'): Promise<BrowserAccount> {
      const accountIdentity = createAccountIdentity(attemptIdentity, role, accountIndex)
      accountIndex += 1
      const context = await browser.newContext({ baseURL: FRONTEND_BASE_URL })
      ownClosable(owner, context, `browser-account-${accountIdentity.username}`)
      const page = await context.newPage()
      return { ...accountIdentity, context, page }
    },
  }
}

export function createAccountFactory(
  playwright: PlaywrightRequest,
  owner: ContextOwner,
  attemptIdentity: TestAttemptIdentity,
): AccountFactory {
  let accountIndex = 0

  return {
    async create(role = 'user'): Promise<TestAccount> {
      const accountIdentity = createAccountIdentity(attemptIdentity, role, accountIndex)
      accountIndex += 1
      const apiContext = await playwright.request.newContext({ baseURL: API_BASE_URL })
      ownDisposable(owner, apiContext, `api-account-${accountIdentity.username}`)

      const response = await apiContext.post('/auth/register', { data: accountIdentity })
      expect(response.status(), await response.text()).toBe(201)
      return { ...accountIdentity, apiContext }
    },

    async createGuest(): Promise<APIRequestContext> {
      const apiContext = await playwright.request.newContext({ baseURL: API_BASE_URL })
      ownDisposable(owner, apiContext, `api-guest-${accountIndex}`)
      accountIndex += 1
      return apiContext
    },
  }
}
