import { describe, expect, it } from 'vitest'

import { readCanonicalPublicUrl } from './config.ts'

describe('readCanonicalPublicUrl', () => {
  it('accepts the expected HTTPS origin', () => {
    expect(
      readCanonicalPublicUrl('APP_URL', 'https://app.wren.test', 'app.wren.test'),
    ).toBe('https://app.wren.test')
  })

  it.each([
    'http://app.wren.test',
    'https://other.wren.test',
    'https://app.wren.test:8443',
    'https://app.wren.test/path',
    'https://user:pass@app.wren.test',
  ])('rejects a non-canonical URL: %s', (value) => {
    expect(() => readCanonicalPublicUrl('APP_URL', value, 'app.wren.test')).toThrow(
      'APP_URL must be the canonical HTTPS origin https://app.wren.test',
    )
  })
})
