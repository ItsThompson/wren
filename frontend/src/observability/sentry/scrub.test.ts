import { describe, expect, it } from 'vitest'

import { scrubSentryEvent } from './scrub'

describe('scrubSentryEvent', () => {
  it('removes credentials from request data and query strings', () => {
    const event = scrubSentryEvent({
      request: {
        url: 'https://api.test/me?token=secret&safe=yes',
        headers: { Authorization: 'Bearer secret', 'x-request-id': 'request-1' },
        query_string: { token: 'secret', safe: 'yes' },
        data: { password: 'secret', title: 'Roadmap' },
      },
      extra: { access_token: 'secret', safe: 'yes' },
    })

    expect(event.request?.url).toContain('token=%5BRedacted%5D')
    expect(event.request?.headers).toEqual({ Authorization: '[Redacted]', 'x-request-id': 'request-1' })
    expect(event.request?.query_string).toEqual({ token: '[Redacted]', safe: 'yes' })
    expect(event.request?.data).toEqual({ password: '[Redacted]', title: 'Roadmap' })
    expect(event.extra).toEqual({ access_token: '[Redacted]', safe: 'yes' })
  })
})
