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
})
