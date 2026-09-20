import { describe, expect, it } from 'vitest'

import { parseE2EInteger } from './playwright.config.ts'

describe('parseE2EInteger', () => {
  it('uses the fallback only when the environment value is absent', () => {
    expect(parseE2EInteger('E2E_WORKERS', undefined, 1, 1)).toBe(1)
    expect(parseE2EInteger('E2E_WORKERS', '02', 1, 1)).toBe(2)
    expect(parseE2EInteger('E2E_RETRIES', '0', 1, 0)).toBe(0)
  })

  it.each(['', '1.5', '2workers', '-1', '+2', ' 2'])('rejects malformed integer value %j', (value) => {
    expect(() => parseE2EInteger('E2E_WORKERS', value, 1, 1)).toThrow('E2E_WORKERS must be a positive integer')
  })

  it('rejects values below the configured minimum', () => {
    expect(() => parseE2EInteger('E2E_WORKERS', '0', 1, 1)).toThrow('E2E_WORKERS must be a positive integer')
    expect(() => parseE2EInteger('E2E_RETRIES', '-1', 1, 0)).toThrow('E2E_RETRIES must be a non-negative integer')
    expect(() => parseE2EInteger('E2E_RETRIES', '0', 1, 0)).not.toThrow()
  })
})
