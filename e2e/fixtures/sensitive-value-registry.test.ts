import { describe, expect, it } from 'vitest'

import { InMemorySensitiveValueRegistry } from './sensitive-value-registry.ts'

describe('InMemorySensitiveValueRegistry', () => {
  it('deduplicates values and clears all categories', () => {
    const registry = new InMemorySensitiveValueRegistry()
    registry.register('token', 'token-value')
    registry.register('token', 'token-value')
    registry.register('authorization-code', 'code-value')
    registry.register('code-verifier', '')

    expect(registry.values()).toEqual(['token-value', 'code-value'])
    registry.clear()
    expect(registry.values()).toEqual([])
  })
})
