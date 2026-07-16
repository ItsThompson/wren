import { describe, expect, it } from 'vitest'

import { keys, type ApiKey } from './keys'

describe('keys', () => {
  it('produces structurally equal tuples for the same inputs', () => {
    expect(keys.dashboard()).toEqual(keys.dashboard())
    expect(keys.roadmap('r1')).toEqual(keys.roadmap('r1'))
    expect(keys.consentContext('a1')).toEqual(keys.consentContext('a1'))
  })

  it('builds the expected path + params tuple for every read surface', () => {
    expect(keys.dashboard()).toEqual(['/me/dashboard'])
    expect(keys.profile('ada')).toEqual(['/users/{handle}', { path: { handle: 'ada' } }])
    expect(keys.roadmap('r1')).toEqual(['/roadmaps/{roadmap_id}', { path: { roadmap_id: 'r1' } }])
    expect(keys.progress('r1')).toEqual([
      '/roadmaps/{roadmap_id}/progress',
      { path: { roadmap_id: 'r1' }, query: { detailed: true } },
    ])
    expect(keys.next('r1')).toEqual(['/roadmaps/{roadmap_id}/next', { path: { roadmap_id: 'r1' } }])
    expect(keys.clients()).toEqual(['/me/clients'])
    expect(keys.consentContext('a1')).toEqual([
      '/authorize/context',
      { query: { auth_request_id: 'a1' } },
    ])
  })

  it('carries detailed: true in the progress key so params are part of cache identity', () => {
    const [, params] = keys.progress('r1')
    expect(params).toEqual({ path: { roadmap_id: 'r1' }, query: { detailed: true } })
  })

  it('never embeds baseUrl: every key path is schema-relative', () => {
    const allKeys: ApiKey[] = [
      keys.dashboard(),
      keys.profile('ada'),
      keys.roadmap('r1'),
      keys.progress('r1'),
      keys.next('r1'),
      keys.clients(),
      keys.consentContext('a1'),
    ]

    for (const [path] of allKeys) {
      expect(path.startsWith('/')).toBe(true)
      expect(path).not.toMatch(/^https?:\/\//)
    }
  })
})
