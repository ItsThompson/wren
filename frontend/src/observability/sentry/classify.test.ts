import { describe, expect, it } from 'vitest'

import { classifyApiFailure, isReportableApiFailure } from './classify'

describe('classifyApiFailure', () => {
  it('treats sub-500 responses as validation outcomes', () => {
    expect(classifyApiFailure({ status: 401 })).toBe('validation')
    expect(classifyApiFailure({ status: 422 })).toBe('validation')
    expect(isReportableApiFailure({ status: 404 })).toBe(false)
  })

  it('reports only valid 5xx responses and network failures', () => {
    expect(classifyApiFailure({ status: 503 })).toBe('upstream')
    expect(classifyApiFailure({ status: 600 })).toBe('validation')
    expect(classifyApiFailure({ status: Number.NaN })).toBe('validation')
    expect(classifyApiFailure({ status: null, error: new Error('offline') })).toBe('network')
    expect(isReportableApiFailure({ status: 500 })).toBe(true)
  })
})
