import type {
  APIRequest,
  APIRequestContext,
  Browser,
  BrowserContext,
  Page,
} from '@playwright/test'
import { expect } from '@playwright/test'

import { API_BASE_URL, FRONTEND_BASE_URL } from '../helpers/config'
import { installRecorderIngestionIdentity } from '../helpers/recorder-client'
import {
  createAccountIdentity,
  type AttemptAccountIdentity,
  type TestAttemptIdentity,
} from './attempt-identity'
import { type ContextOwner, ownClosable, ownDisposable } from './context-owner'
import type { SensitiveValueRegistry } from './sensitive-value-registry'

export interface TestAccount extends AttemptAccountIdentity {
  apiContext: APIRequestContext
}

export interface BrowserAccount extends AttemptAccountIdentity {
  context: BrowserContext
  page: Page
  registerSensitiveCookies(): Promise<void>
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
  sensitiveValues: SensitiveValueRegistry | undefined,
  queryIdentity: string,
): BrowserAccountFactory {
  let accountIndex = 0

  return {
    async create(role = 'human'): Promise<BrowserAccount> {
      const accountIdentity = createAccountIdentity(attemptIdentity, role, accountIndex)
      accountIndex += 1
      sensitiveValues?.register('username', accountIdentity.username)
      sensitiveValues?.register('email', accountIdentity.email)
      sensitiveValues?.register('password', accountIdentity.password)
      const context = await browser.newContext({ baseURL: FRONTEND_BASE_URL })
      await installRecorderIngestionIdentity(context, queryIdentity)
      if (sensitiveValues !== undefined) {
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
      ownClosable(owner, context, `browser-account-${accountIdentity.username}`)
      const page = await context.newPage()
      return {
        ...accountIdentity,
        context,
        page,
        registerSensitiveCookies: async (): Promise<void> => {
          for (const cookie of await context.cookies()) {
            sensitiveValues?.register('session-cookie', `${cookie.name}=${cookie.value}`)
            sensitiveValues?.register('session-cookie', cookie.value)
          }
        },
      }
    },
  }
}

export function createAccountFactory(
  playwright: PlaywrightRequest,
  owner: ContextOwner,
  attemptIdentity: TestAttemptIdentity,
  sensitiveValues?: SensitiveValueRegistry,
): AccountFactory {
  let accountIndex = 0

  return {
    async create(role = 'user'): Promise<TestAccount> {
      const accountIdentity = createAccountIdentity(attemptIdentity, role, accountIndex)
      accountIndex += 1
      sensitiveValues?.register('username', accountIdentity.username)
      sensitiveValues?.register('email', accountIdentity.email)
      sensitiveValues?.register('password', accountIdentity.password)
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
