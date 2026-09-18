import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MergedOptions, MiddlewareCallbackParams } from 'openapi-fetch'

import { createApiReportingMiddleware, operationIdFor } from './apiMiddleware'
import { reportApiFailure } from './report'

vi.mock('./report', () => ({
  reportApiFailure: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
})

// Complete callback options even though the reporting middleware reads none of
// them. This avoids forcing a partial external-library object past the checker.
const unusedClientOptions: MergedOptions = {
  baseUrl: 'https://api.test',
  parseAs: 'json',
  querySerializer: () => '',
  bodySerializer: (body) => body,
  pathSerializer: (pathname) => pathname,
  fetch: globalThis.fetch,
}

function baseParams(schemaPath: string): MiddlewareCallbackParams {
  return {
    request: new Request('https://api.test' + (schemaPath.includes('unknown') ? '/unknown' : '/me/dashboard')),
    schemaPath,
    params: {},
    id: 'test-1',
    options: unusedClientOptions,
  }
}

describe('createApiReportingMiddleware', () => {
  it('reports unknown method/schema-path pairs through a field-name diagnostic', async () => {
    const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { middleware } = createApiReportingMiddleware()

    await middleware.onResponse?.({ ...baseParams('/unknown'), response: new Response(null, { status: 503 }) })
    middleware.onError?.({ ...baseParams('/unknown'), error: new TypeError('offline') })

    expect(reportApiFailure).not.toHaveBeenCalled()
    expect(consoleWarn).toHaveBeenCalledWith('reporting_contract_invalid', { fields: ['operationId'] })
    consoleWarn.mockRestore()
  })

  it('reports a rejected raw retry once and rethrows the same object', async () => {
    const { observeRetryRejection } = createApiReportingMiddleware()
    const rejection = new TypeError('offline')
    const attempt = vi.fn(async () => {
      throw rejection
    })

    await expect(
      observeRetryRejection(attempt, {
        method: 'GET',
        schemaPath: '/me/dashboard',
        url: 'https://api.test/me/dashboard',
      }),
    ).rejects.toBe(rejection)

    expect(reportApiFailure).toHaveBeenCalledTimes(1)
    expect(reportApiFailure).toHaveBeenCalledWith({
      error: rejection,
      status: null,
      operationId: 'get_dashboard_me_dashboard_get',
      method: 'GET',
      schemaPath: '/me/dashboard',
      url: 'https://api.test/me/dashboard',
    })
  })

  it('still rethrows the original rejection when the operation is unknown', async () => {
    const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { observeRetryRejection } = createApiReportingMiddleware()
    const rejection = new TypeError('offline')

    await expect(
      observeRetryRejection(async () => {
        throw rejection
      }, { method: 'GET', schemaPath: '/unknown', url: 'https://api.test/unknown' }),
    ).rejects.toBe(rejection)

    expect(consoleWarn).toHaveBeenCalledWith('reporting_contract_invalid', { fields: ['operationId'] })
    consoleWarn.mockRestore()
  })

  it('returns the retried response untouched when the retry succeeds', async () => {
    const { observeRetryRejection } = createApiReportingMiddleware()
    const retried = new Response(null, { status: 200 })

    const result = await observeRetryRejection(async () => retried, {
      method: 'GET',
      schemaPath: '/me/dashboard',
      url: 'https://api.test/me/dashboard',
    })

    expect(result).toBe(retried)
    expect(reportApiFailure).not.toHaveBeenCalled()
  })

  it('exposes a strict registry lookup for operation identity', () => {
    expect(operationIdFor('get', '/me/dashboard')).toBe('get_dashboard_me_dashboard_get')
  })
})
