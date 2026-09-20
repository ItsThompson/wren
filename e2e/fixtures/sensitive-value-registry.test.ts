import { chmod, mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises'
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

  it('merges snapshots atomically with restricted modes on existing paths', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'wren-sensitive-test-'))
    const path = join(directory, 'worker.json')
    const temporary = `${path}.tmp-${process.pid}`
    try {
      await chmod(directory, 0o755)
      await writeFile(path, JSON.stringify({ username: ['first-user'] }))
      await chmod(path, 0o644)
      await writeFile(temporary, 'stale snapshot')
      await chmod(temporary, 0o644)

      const registry = new InMemorySensitiveValueRegistry()
      registry.register('email', 'second@example.com')
      await persistSensitiveValueSnapshot(registry, path)

      expect((await stat(directory)).mode & 0o777).toBe(0o700)
      expect((await stat(path)).mode & 0o777).toBe(0o600)
      expect(JSON.parse(await readFile(path, 'utf8'))).toEqual({
        username: ['first-user'],
        email: ['second@example.com'],
      })
      await expect(stat(temporary)).rejects.toMatchObject({ code: 'ENOENT' })
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
      expect((await stat(path)).mode & 0o777).toBe(0o600)
    } finally {
      await rm(directory, { recursive: true, force: true })
    }
  })
})
