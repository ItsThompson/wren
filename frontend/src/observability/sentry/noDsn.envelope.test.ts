import * as Sentry from '@sentry/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { initSentry } from './init'

describe('real-SDK no-DSN initialization', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllEnvs()
  })

  it('stays uninitialized, silent, and transport-free', () => {
    expect(Sentry.getClient()).toBeUndefined()
    vi.stubEnv('VITE_SENTRY_DSN', '')
    const consoleInfo = vi.spyOn(console, 'info').mockImplementation(() => {})
    const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    initSentry()

    expect(Sentry.getClient()).toBeUndefined()
    expect(consoleInfo).not.toHaveBeenCalled()
    expect(consoleWarn).not.toHaveBeenCalled()
    expect(consoleError).not.toHaveBeenCalled()
  })
})
