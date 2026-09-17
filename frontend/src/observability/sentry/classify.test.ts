import { describe, expect, it } from 'vitest'

import { classifyApiFailure, isReportableApiFailure } from './classify'

describe('classifyApiFailure', () => {
  it('treats client responses as expected application outcomes', () => {
    expect(classifyApiFailure({ status: 401 })).toBe('expected')
    expect(classifyApiFailure({ status: 422 })).toBe('expected')
    expect(isReportableApiFailure({ status: 404 })).toBe(false)
  })

  it('reports server responses and network failures', () => {
    expect(classifyApiFailure({ status: 503 })).toBe('server')
    expect(classifyApiFailure({ status: null, error: new Error('offline') })).toBe('network')
    expect(isReportableApiFailure({ status: 500 })).toBe(true)
  })
})
