import { describe, expect, it } from 'vitest'

import { ResourceOwner } from './resource-owner.ts'

describe('ResourceOwner', () => {
  it('closes resources in reverse order and continues after a failure', async () => {
    const owner = new ResourceOwner()
    const closed: string[] = []

    owner.add(() => {
      closed.push('browser')
    })
    owner.add(async () => {
      closed.push('api')
      throw new Error('api close failed')
    })
    owner.add(() => {
      closed.push('callback')
    })

    await expect(owner.close()).rejects.toThrow('api close failed')
    expect(closed).toEqual(['callback', 'api', 'browser'])

    await owner.close()
    expect(closed).toEqual(['callback', 'api', 'browser'])
  })
})
