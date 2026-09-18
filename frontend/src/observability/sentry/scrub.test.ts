import { describe, expect, it } from 'vitest'

import { scrubSentryEvent } from './scrub'

describe('scrubSentryEvent', () => {
  it('removes request-derived fields and exception payloads', () => {
    const event = scrubSentryEvent({
      request: { url: 'https://api.test/me?token=secret' },
      breadcrumbs: [{ message: 'secret request' }],
      extra: { access_token: 'secret' },
      exception: {
        values: [
          {
            type: 'Error',
            value: 'secret exception',
            mechanism: { type: 'generic', handled: false },
            stacktrace: { frames: [{ filename: 'app.ts', vars: { secret: 'value' } }] },
          },
        ],
      },
    })

    expect(event.request).toBeUndefined()
    expect(event.breadcrumbs).toBeUndefined()
    expect(event.extra).toBeUndefined()
    expect(event.exception?.values?.[0].value).toBe('[Redacted exception]')
    expect(event.exception?.values?.[0].mechanism).toBeUndefined()
    expect(event.exception?.values?.[0].stacktrace?.frames?.[0].vars).toBeUndefined()
  })

  it('keeps only allowlisted bounded tags', () => {
    const event = scrubSentryEvent({
      tags: {
        service: 'wren-web',
        'api.operation': 'get_dashboard_me_dashboard_get',
        code: 'UPSTREAM_UNAVAILABLE',
        unsafe: 'https://api.test?token=secret',
        expected: '',
      },
    })

    expect(event.tags).toEqual({
      service: 'wren-web',
      'api.operation': 'get_dashboard_me_dashboard_get',
      code: 'UPSTREAM_UNAVAILABLE',
    })
  })

  it('keeps only allowlisted scalar report-context keys', () => {
    const event = scrubSentryEvent({
      contexts: {
        report: {
          method: 'GET',
          status: 503,
          url: 'https://api.test/me?token=secret',
          body: { password: 'secret' },
          nested: { deep: { value: 'secret' } },
        },
      },
    })

    expect(event.contexts).toEqual({ report: { method: 'GET', status: 503 } })
  })

  it('deletes every non-report context', () => {
    const event = scrubSentryEvent({
      contexts: {
        runtime_debug: { trace: 't', data: { url: 'https://api.test?token=secret' } },
        response: { headers: { authorization: 'secret' } },
        report: { method: 'POST', status: 401 },
      },
    })

    expect(event.contexts).toEqual({ report: { method: 'POST', status: 401 } })
  })

  it('drops non-scalar or absent report contexts entirely', () => {
    const scalarViolation = scrubSentryEvent({ contexts: { report: { method: ['G', 'E', 'T'] } } })
    expect(scalarViolation.contexts).toEqual({ report: {} })

    const absent = scrubSentryEvent({ contexts: { other: { value: 1 } } })
    expect(absent.contexts).toEqual({})
  })
})
