import type { APIRequestContext, Browser, Page } from '@playwright/test'
import { describe, expect, it, vi } from 'vitest'

import { createAttemptIdentity } from './attempt-identity.ts'
import { createAccountFactory, createBrowserAccountFactory } from './account-fixture.ts'
import { OwnedContextResources } from './context-owner.ts'
import { InMemorySensitiveValueRegistry } from './sensitive-value-registry.ts'

function buildAttemptIdentity() {
  return createAttemptIdentity({
    runId: 'run-123',
    projectName: 'chromium',
    file: 'account.spec.ts',
    title: 'creates accounts',
    parallelIndex: 0,
    retry: 0,
    nonce: 'fixed123',
  })
}

describe('account fixture factory', () => {
  it('registers unique attempt-scoped accounts and owns each API context', async () => {
    const disposeCalls: Array<ReturnType<typeof vi.fn>> = []
    const registeredPayloads: Array<Record<string, string>> = []
    const request = {
      newContext: vi.fn(async () => {
        const dispose = vi.fn(async () => undefined)
        const post = vi.fn(async (_path: string, options: { data: Record<string, string> }) => {
          registeredPayloads.push(options.data)
          return { status: () => 201, text: async () => '' }
        })
        const context = {
          post,
          dispose,
        } as unknown as APIRequestContext
        disposeCalls.push(dispose)
        return context
      }),
    }
    const owner = new OwnedContextResources()
    const sensitiveValues = new InMemorySensitiveValueRegistry()
    const factory = createAccountFactory({ request }, owner, buildAttemptIdentity(), sensitiveValues)

    const first = await factory.create('owner')
    const second = await factory.create('owner')

    expect(first.username).not.toBe(second.username)
    expect(first.email).toBe(`${first.username}@example.com`)
    expect(request.newContext).toHaveBeenCalledTimes(2)
    expect(sensitiveValues.snapshot().email).toEqual([first.email, second.email])
    expect(sensitiveValues.snapshot().password).toEqual([first.password])
    expect(registeredPayloads).toEqual([
      { username: first.username, email: first.email, password: first.password },
      { username: second.username, email: second.email, password: second.password },
    ])
    await owner.closeAll()
    expect(disposeCalls.every((dispose) => dispose.mock.calls.length === 1)).toBe(true)
  })

  it('creates a browser account without registering through an API helper', async () => {
    const close = vi.fn(async () => undefined)
    const page = {} as Page
    const newPage = vi.fn(async (): Promise<Page> => page)
    const route = vi.fn(async () => undefined)
    const browser = {
      newContext: vi.fn(async () => ({ close, newPage, on: vi.fn(), route })),
    } as unknown as Pick<Browser, 'newContext'>
    const owner = new OwnedContextResources()
    const sensitiveValues = new InMemorySensitiveValueRegistry()
    const factory = createBrowserAccountFactory(
      browser,
      owner,
      buildAttemptIdentity(),
      sensitiveValues,
      'e2e-test-recorder',
    )

    const account = await factory.create('human')

    expect(account.email).toBe(`${account.username}@example.com`)
    expect(sensitiveValues.snapshot().username).toEqual([account.username])
    expect(sensitiveValues.snapshot().email).toEqual([account.email])
    expect(sensitiveValues.snapshot().password).toEqual([account.password])
    expect(browser.newContext).toHaveBeenCalledWith({ baseURL: 'https://app.wren.test' })
    expect(route).toHaveBeenCalledWith('**/_e2e/sentry/api/**', expect.any(Function))
    expect(newPage).toHaveBeenCalledOnce()
    expect(account.page).toBe(page)
    await owner.closeAll()
    expect(close).toHaveBeenCalledOnce()
  })

  it('keeps the context owned when account registration fails', async () => {
    const dispose = vi.fn(async () => undefined)
    const request = {
      newContext: vi.fn(async () => {
        return {
          post: vi.fn(async () => ({ status: () => 500, text: async () => 'failed' })),
          dispose,
        } as unknown as APIRequestContext
      }),
    }
    const owner = new OwnedContextResources()
    const factory = createAccountFactory({ request }, owner, buildAttemptIdentity())

    await expect(factory.create('broken')).rejects.toThrow()
    await owner.closeAll()

    expect(dispose).toHaveBeenCalledOnce()
  })
})
