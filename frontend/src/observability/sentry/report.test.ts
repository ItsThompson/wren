import { beforeEach, describe, expect, it, vi } from 'vitest'

const { captureException, setTag, setExtra } = vi.hoisted(() => ({
  captureException: vi.fn(),
  setTag: vi.fn(),
  setExtra: vi.fn(),
}))
vi.mock('@sentry/react', () => ({
  captureException,
  withScope: (callback: (scope: { setTag: typeof setTag; setExtra: typeof setExtra }) => void) =>
    callback({ setTag, setExtra }),
}))

import { reportApiFailure } from './report'

describe('reportApiFailure', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('does not report expected client failures', () => {
    const kind = reportApiFailure({
      status: 409,
      operationId: 'update_roadmap',
      method: 'PATCH',
      url: 'https://api.test/roadmaps/one',
    })

    expect(kind).toBe('expected')
    expect(captureException).not.toHaveBeenCalled()
  })

  it('reports server failures with operation context', () => {
    const error = new Error('upstream unavailable')
    const kind = reportApiFailure({
      error,
      status: 503,
      operationId: 'get_dashboard',
      method: 'GET',
      url: 'https://api.test/me/dashboard',
    })

    expect(kind).toBe('server')
    expect(setTag).toHaveBeenCalledWith('api.operation', 'get_dashboard')
    expect(setTag).toHaveBeenCalledWith('api.failure_kind', 'server')
    expect(setExtra).toHaveBeenCalledWith('api.status', 503)
    expect(captureException).toHaveBeenCalledWith(error)
  })
})
