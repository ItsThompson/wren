import { StrictMode } from 'react'

import * as Sentry from '@sentry/react'
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { beforeSendSentryEvent } from '@/observability/sentry'
import { TEST_SENTRY_DSN, makeRecordingTransport } from '@/test/sentryRecording'

import { AppErrorBoundary } from './AppErrorBoundary'

const events: Sentry.Event[] = []

function initRecordingTransport(): void {
  Sentry.init({
    dsn: TEST_SENTRY_DSN,
    transport: makeRecordingTransport(events),
    beforeSend: beforeSendSentryEvent,
    sendDefaultPii: false,
    defaultIntegrations: [],
    integrations: [Sentry.linkedErrorsIntegration()],
    enableLogs: false,
    maxBreadcrumbs: 0,
    tracesSampleRate: 0,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
  })
}

function BrokenChild({ message }: { message: string }): null {
  throw new Error(message)
}

describe('AppErrorBoundary with the real SDK', () => {
  beforeEach(() => {
    events.length = 0
    initRecordingTransport()
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(async () => {
    await Sentry.close()
    vi.restoreAllMocks()
  })

  it('captures exactly one render envelope, renders the fallback, and preserves the error object', async () => {
    render(
      <StrictMode>
        <AppErrorBoundary>
          <BrokenChild message="render failed" />
        </AppErrorBoundary>
      </StrictMode>,
    )
    await Sentry.flush()

    expect(events).toHaveLength(1)
    const [event] = events
    expect(event.tags?.['api.operation']).toBe('render.app')
    expect(event.tags?.['api.failure_kind']).toBe('internal')

    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('does not add a cause property to a cause-less application error', async () => {
    const thrown = new Error('render failed without cause')

    function ChildWithoutCause(): null {
      throw thrown
    }

    expect(Object.prototype.hasOwnProperty.call(thrown, 'cause')).toBe(false)
    render(
      <AppErrorBoundary>
        <ChildWithoutCause />
      </AppErrorBoundary>,
    )
    await Sentry.flush()

    expect(events).toHaveLength(1)
    expect(thrown.cause).toBeUndefined()
    expect(Object.prototype.hasOwnProperty.call(thrown, 'cause')).toBe(false)
  })

  it('restores a pre-existing cause chain after the SDK capture', async () => {
    const originalCause = new Error('original application cause')
    const thrown: { error?: Error } = {}

    function ChildWithCause(): null {
      const error = new Error('render failed with cause')
      error.cause = originalCause
      thrown.error = error
      throw error
    }

    render(
      <AppErrorBoundary>
        <ChildWithCause />
      </AppErrorBoundary>,
    )
    await Sentry.flush()

    expect(events).toHaveLength(1)
    const error = thrown.error
    expect(error).toBeInstanceOf(Error)
    // Identity and the original cause survive the SDK's capture untouched:
    // no React ErrorBoundary cause was appended anywhere in the chain.
    expect(error!.cause).toBe(originalCause)
    expect((error!.cause as Error).cause).toBeUndefined()
    let current: unknown = error
    while (current instanceof Error) {
      expect(current.name).not.toContain('React ErrorBoundary')
      current = current.cause
    }
  })
})
