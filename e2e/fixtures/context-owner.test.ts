import { describe, expect, it } from 'vitest'

import { OwnedContextResources, ResourceCleanupError } from './context-owner.ts'

describe('OwnedContextResources', () => {
  it('closes owned resources in reverse order and reports all failures', async () => {
    const owner = new OwnedContextResources()
    const closed: string[] = []

    owner.own({ name: 'browser', close: async () => { closed.push('browser') } })
    owner.own({
      name: 'api',
      close: async () => {
        closed.push('api')
        throw new Error('api close failed')
      },
    })
    owner.own({
      name: 'callback',
      close: async () => {
        closed.push('callback')
        throw new Error('callback close failed')
      },
    })

    const failure = await owner.closeAll().catch((error: unknown) => error)

    expect(closed).toEqual(['callback', 'api', 'browser'])
    expect(failure).toBeInstanceOf(ResourceCleanupError)
    expect(failure).toBeInstanceOf(AggregateError)
    expect((failure as AggregateError).errors).toHaveLength(2)
  })

  it('closes resources created before a later fixture step fails', async () => {
    const owner = new OwnedContextResources()
    const closed: string[] = []
    owner.own({ name: 'api', close: async () => { closed.push('api') } })

    await expect(
      (async () => {
        throw new Error('browser creation failed')
      })(),
    ).rejects.toThrow('browser creation failed')
    await owner.closeAll()

    expect(closed).toEqual(['api'])
  })

  it('closes resources exactly once when a fixture body times out', async () => {
    const owner = new OwnedContextResources()
    let closeCount = 0
    owner.own({
      name: 'listener',
      close: async () => {
        closeCount += 1
      },
    })

    const fixtureFinalizer = async (): Promise<void> => {
      try {
        await Promise.reject(new Error('test timed out'))
      } finally {
        await owner.closeAll()
      }
    }

    await expect(fixtureFinalizer()).rejects.toThrow('test timed out')
    await owner.closeAll()

    expect(closeCount).toBe(1)
  })
})
