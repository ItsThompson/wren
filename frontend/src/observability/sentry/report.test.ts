import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { captureException, setTag, setContext, setLevel, withScope } = vi.hoisted(() => ({
  captureException: vi.fn(),
  setTag: vi.fn(),
  setContext: vi.fn(),
  setLevel: vi.fn(),
  withScope: vi.fn(),
}))
vi.mock('@sentry/react', () => ({
  captureException,
  withScope: (
    callback: (scope: {
      setTag: typeof setTag
      setContext: typeof setContext
      setLevel: typeof setLevel
    }) => void,
  ) => withScope(callback),
}))

import { applyRenderCaptureTags, isKnownBrowserFailureKind, reportApiFailure } from './report'

function invokeScope(callback: (scope: unknown) => void): void {
  callback({ setTag, setContext, setLevel })
}
withScope.mockImplementation(invokeScope)

describe('reportApiFailure', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('accepts only the closed browser failure taxonomy', () => {
    expect(isKnownBrowserFailureKind('validation')).toBe(true)
    expect(isKnownBrowserFailureKind('upstream')).toBe(true)
    expect(isKnownBrowserFailureKind('internal')).toBe(true)
    expect(isKnownBrowserFailureKind('network')).toBe(true)
    expect(isKnownBrowserFailureKind('expected')).toBe(false)
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

  it('reports server failures with operation context and closed report context', () => {
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
    expect(setContext).toHaveBeenCalledWith('report', { method: 'GET', status: 503 })
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

  it('rejects the fixed render operation paired with valid API metadata', () => {
    const kind = reportApiFailure({
      status: 503,
      operationId: 'render.app',
      method: 'GET',
      schemaPath: '/me/dashboard',
      url: 'https://api.test/me/dashboard',
    })

    expect(kind).toBe('upstream')
    expect(captureException).not.toHaveBeenCalled()
    expect(console.warn).toHaveBeenCalledWith('reporting_contract_invalid', { fields: ['operationId'] })
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

  it('skips invalid operation metadata with a field-name-only diagnostic', () => {
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

  it('omits unknown, reserved, and oversized optional tags without logging values', () => {
    reportApiFailure({
      status: 503,
      operationId: 'get_dashboard_me_dashboard_get',
      method: 'GET',
      schemaPath: '/me/dashboard',
      url: 'https://api.test/me/dashboard',
      tags: {
        code: 'INTERNAL',
        unknown_tag: 'value',
        expected: 'true',
        reason: 'r'.repeat(201),
        '': 'empty-key',
      },
    })

    expect(setTag).toHaveBeenCalledWith('code', 'INTERNAL')
    expect(setTag).not.toHaveBeenCalledWith('unknown_tag', 'value')
    expect(setTag).not.toHaveBeenCalledWith('expected', 'true')
    expect(setTag).not.toHaveBeenCalledWith('reason', expect.anything())
    const warned = vi.mocked(console.warn).mock.calls.map((call) => call[0])
    expect(warned).not.toContain('reporting_contract_invalid')
  })

  it('never throws when the SDK fails synchronously', () => {
    withScope.mockImplementationOnce(() => {
      throw new Error('SDK serialization failure')
    })

    const kind = reportApiFailure({
      status: 503,
      operationId: 'get_dashboard_me_dashboard_get',
      method: 'GET',
      schemaPath: '/me/dashboard',
      url: 'https://api.test/me/dashboard',
    })

    expect(kind).toBe('upstream')
    expect(console.warn).toHaveBeenCalledWith('reporting_failed')
  })

  it('enriches render captures with the fixed render taxonomy', () => {
    const scope = { setTag }
    applyRenderCaptureTags(scope)
    expect(setTag).toHaveBeenCalledWith('api.operation', 'render.app')
    expect(setTag).toHaveBeenCalledWith('api.failure_kind', 'internal')
  })
})
