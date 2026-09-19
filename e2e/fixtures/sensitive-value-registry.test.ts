import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import { InMemorySensitiveValueRegistry, persistSensitiveValueSnapshot } from './sensitive-value-registry.ts'

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

  it('isolates live values across session registries while retaining the snapshot sink', () => {
    const snapshot = new InMemorySensitiveValueRegistry()
    const firstSession = new InMemorySensitiveValueRegistry(snapshot)
    const secondSession = new InMemorySensitiveValueRegistry(snapshot)
    firstSession.register('token', 'first-token')
    secondSession.register('token', 'second-token')

    firstSession.clear()

    expect(firstSession.values()).toEqual([])
    expect(secondSession.values()).toEqual(['second-token'])
    expect(snapshot.values()).toEqual(['first-token', 'second-token'])
  })

  it('merges snapshots through an atomic job-local file', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'wren-sensitive-test-'))
    const path = join(directory, 'worker.json')
    try {
      const first = new InMemorySensitiveValueRegistry()
      first.register('username', 'first-user')
      await persistSensitiveValueSnapshot(first, path)
      const second = new InMemorySensitiveValueRegistry()
      second.register('email', 'second@example.com')
      await persistSensitiveValueSnapshot(second, path)

      expect(JSON.parse(await readFile(path, 'utf8'))).toEqual({
        username: ['first-user'],
        email: ['second@example.com'],
      })
    } finally {
      await rm(directory, { recursive: true, force: true })
    }
  })

  it('rejects a malformed existing snapshot instead of replacing it', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'wren-sensitive-test-'))
    const path = join(directory, 'worker.json')
    try {
      await writeFile(path, '{not-json')
      await expect(persistSensitiveValueSnapshot(new InMemorySensitiveValueRegistry(), path)).rejects.toThrow()
      expect(await readFile(path, 'utf8')).toBe('{not-json')
    } finally {
      await rm(directory, { recursive: true, force: true })
    }
  })
})
