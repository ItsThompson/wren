import type { APIRequest, APIRequestContext } from '@playwright/test'
import { expect } from '@playwright/test'

import { API_BASE_URL } from '../helpers/config'
import {
  createAccountIdentity,
  type AttemptAccountIdentity,
  type TestAttemptIdentity,
} from './attempt-identity'
import { type ContextOwner, ownDisposable } from './context-owner'

export interface TestAccount extends AttemptAccountIdentity {
  apiContext: APIRequestContext
}

export interface AccountFactory {
  create(role?: string): Promise<TestAccount>
  createGuest(): Promise<APIRequestContext>
}

interface PlaywrightRequest {
  request: Pick<APIRequest, 'newContext'>
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
