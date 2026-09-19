import type { APIRequestContext } from '@playwright/test'
import { describe, expect, it, vi } from 'vitest'

import { createAttemptIdentity } from './attempt-identity.ts'
import { createAccountFactory } from './account-fixture.ts'
import { OwnedContextResources } from './context-owner.ts'

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
    const request = {
      newContext: vi.fn(async () => {
        const dispose = vi.fn(async () => undefined)
        const context = {
          post: vi.fn(async () => ({ status: () => 201, text: async () => '' })),
          dispose,
        } as unknown as APIRequestContext
        disposeCalls.push(dispose)
        return context
      }),
    }
    const owner = new OwnedContextResources()
    const factory = createAccountFactory({ request }, owner, buildAttemptIdentity())

    const first = await factory.create('owner')
    const second = await factory.create('owner')

    expect(first.username).not.toBe(second.username)
    expect(first.email).toBe(`${first.username}@example.com`)
    expect(request.newContext).toHaveBeenCalledTimes(2)
    await owner.closeAll()
    expect(disposeCalls.every((dispose) => dispose.mock.calls.length === 1)).toBe(true)
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
