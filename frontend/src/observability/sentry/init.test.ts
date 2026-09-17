import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { init } = vi.hoisted(() => ({ init: vi.fn() }))
vi.mock('@sentry/react', () => ({ init }))

import { initSentry } from './init'

describe('initSentry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.unstubAllEnvs()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('leaves Sentry disabled when no DSN is configured', () => {
    vi.stubEnv('VITE_SENTRY_DSN', '')
    initSentry()
    expect(init).not.toHaveBeenCalled()
  })

  it('initializes Sentry with the configured DSN and scrubber', () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://public@example.ingest.sentry.io/1')
    vi.stubEnv('VITE_SENTRY_RELEASE', 'release-1')
    initSentry()

    expect(init).toHaveBeenCalledWith(
      expect.objectContaining({
        dsn: 'https://public@example.ingest.sentry.io/1',
        release: 'release-1',
        sendDefaultPii: false,
        beforeSend: expect.any(Function),
      }),
    )
  })
})
