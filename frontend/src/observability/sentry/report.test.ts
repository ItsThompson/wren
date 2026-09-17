import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { captureException, setTag, setExtra, setLevel } = vi.hoisted(() => ({
  captureException: vi.fn(),
  setTag: vi.fn(),
  setExtra: vi.fn(),
  setLevel: vi.fn(),
}))
vi.mock('@sentry/react', () => ({
  captureException,
  withScope: (
    callback: (scope: {
      setTag: typeof setTag
      setExtra: typeof setExtra
      setLevel: typeof setLevel
    }) => void,
  ) => callback({ setTag, setExtra, setLevel }),
}))

import { isKnownBrowserFailureKind, reportApiFailure } from './report'

describe('reportApiFailure', () => {
  it('accepts only the closed browser failure taxonomy', () => {
    expect(isKnownBrowserFailureKind('validation')).toBe(true)
    expect(isKnownBrowserFailureKind('upstream')).toBe(true)
    expect(isKnownBrowserFailureKind('internal')).toBe(true)
    expect(isKnownBrowserFailureKind('network')).toBe(true)
    expect(isKnownBrowserFailureKind('expected')).toBe(false)
  })

  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('marks validation failures for the beforeSend drop', () => {
    const kind = reportApiFailure({
      status: 409,
      operationId: 'patch_roadmap_roadmaps__roadmap_id__patch',
      method: 'PATCH',
      schemaPath: '/roadmaps/{roadmap_id}',
      url: 'https://api.test/roadmaps/one',
    })

    expect(kind).toBe('validation')
    expect(setTag).toHaveBeenCalledWith('expected', 'true')
    expect(setTag).toHaveBeenCalledWith('api.failure_kind', 'validation')
    expect(captureException).toHaveBeenCalledOnce()
  })

  it('reports server failures with operation context', () => {
    const error = new Error('upstream unavailable')
    const kind = reportApiFailure({
      error,
      status: 503,
      operationId: 'get_dashboard_me_dashboard_get',
      method: 'GET',
      schemaPath: '/me/dashboard',
      url: 'https://api.test/me/dashboard',
    })

    expect(kind).toBe('upstream')
    expect(setTag).toHaveBeenCalledWith('api.operation', 'get_dashboard_me_dashboard_get')
    expect(setTag).toHaveBeenCalledWith('api.domain', 'accounts')
    expect(setTag).toHaveBeenCalledWith('api.failure_kind', 'upstream')
    expect(setExtra).toHaveBeenCalledWith('api.status', 503)
    expect(setLevel).not.toHaveBeenCalled()
    expect(captureException).toHaveBeenCalledWith(error)
  })

  it('reports network failures at warning level', () => {
    const error = new TypeError('offline')
    const kind = reportApiFailure({
      error,
      status: null,
      operationId: 'get_dashboard_me_dashboard_get',
      method: 'GET',
      schemaPath: '/me/dashboard',
      url: 'https://api.test/me/dashboard',
    })

    expect(kind).toBe('network')
    expect(setLevel).toHaveBeenCalledWith('warning')
    expect(captureException).toHaveBeenCalledWith(error)
  })

  it('rejects a mismatched valid operation and method without changing the failure outcome', () => {
    const kind = reportApiFailure({
      status: 503,
      operationId: 'get_dashboard_me_dashboard_get',
      method: 'POST',
      schemaPath: '/me/dashboard',
      url: 'https://api.test/me/dashboard',
    })

    expect(kind).toBe('upstream')
    expect(captureException).not.toHaveBeenCalled()
    expect(console.warn).toHaveBeenCalledWith('reporting_contract_invalid', { fields: ['method'] })
  })

  it('rejects invalid domain and kind values without changing the failure outcome', () => {
    const kind = reportApiFailure({
      status: 503,
      operationId: 'get_dashboard_me_dashboard_get',
      method: 'GET',
      schemaPath: '/me/dashboard',
      url: 'https://api.test/me/dashboard',
      domain: 'not-a-domain',
      kind: 'not-a-kind',
    })

    expect(kind).toBe('upstream')
    expect(captureException).not.toHaveBeenCalled()
    expect(console.warn).toHaveBeenCalledWith('reporting_contract_invalid', {
      fields: ['domain', 'kind'],
    })
  })

  it('skips invalid operation metadata without changing the failure outcome', () => {
    const kind = reportApiFailure({
      status: 500,
      operationId: 'unknown_operation',
      method: 'GET',
      schemaPath: '/unknown',
      url: 'https://api.test/unknown',
    })

    expect(kind).toBe('upstream')
    expect(captureException).not.toHaveBeenCalled()
    expect(console.warn).toHaveBeenCalledWith('reporting_contract_invalid', { fields: ['operationId'] })
  })
})
