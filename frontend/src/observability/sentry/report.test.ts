import { beforeEach, describe, expect, it, vi } from 'vitest'

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

import { reportApiFailure } from './report'

describe('reportApiFailure', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('marks expected client failures for the beforeSend drop', () => {
    const kind = reportApiFailure({
      status: 409,
      operationId: 'patch_roadmap_roadmaps__roadmap_id__patch',
      method: 'PATCH',
      url: 'https://api.test/roadmaps/one',
    })

    expect(kind).toBe('expected')
    expect(setTag).toHaveBeenCalledWith('expected', 'true')
    expect(captureException).toHaveBeenCalledOnce()
  })

  it('reports server failures with operation context', () => {
    const error = new Error('upstream unavailable')
    const kind = reportApiFailure({
      error,
      status: 503,
      operationId: 'get_dashboard_me_dashboard_get',
      method: 'GET',
      url: 'https://api.test/me/dashboard',
    })

    expect(kind).toBe('server')
    expect(setTag).toHaveBeenCalledWith('api.operation', 'get_dashboard_me_dashboard_get')
    expect(setTag).toHaveBeenCalledWith('api.failure_kind', 'server')
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
      url: 'https://api.test/me/dashboard',
    })

    expect(kind).toBe('network')
    expect(setLevel).toHaveBeenCalledWith('warning')
    expect(captureException).toHaveBeenCalledWith(error)
  })

  it('rejects operations outside the generated registry', () => {
    expect(() =>
      reportApiFailure({
        status: 500,
        operationId: 'unknown_operation' as never,
        method: 'GET',
        url: 'https://api.test/unknown',
      }),
    ).toThrow('Unknown reporting operation: unknown_operation')
    expect(captureException).not.toHaveBeenCalled()
  })
})
