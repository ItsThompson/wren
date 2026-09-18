import * as Sentry from '@sentry/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { TEST_SENTRY_DSN, makeRecordingTransport } from '@/test/sentryRecording'

import { beforeSendSentryEvent } from './init'
import { reportApiFailure } from './report'

// Assembled at runtime so the assembled sentinel strings never appear verbatim
// in this file's source: serialized stack frames would otherwise inline them.
const SENTINEL_QUERY = 'SENTINEL_' + 'QUERY_TOKEN'
const SENTINEL_MSG = 'SENTINEL_' + 'MESSAGE_TOKEN'
const SENTINEL_CAUSE = 'SENTINEL_' + 'CAUSE_TOKEN'

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
    environment: 'test',
    release: 'wren-web@websha123',
    initialScope: {
      tags: { service: 'wren-web', surface: 'web', runtime: 'browser' },
    },
  })
}

function reportUpstreamFailure(error?: unknown, tags?: Record<string, string>): void {
  reportApiFailure({
    ...(error !== undefined ? { error } : {}),
    ...(tags !== undefined ? { tags } : {}),
    status: 503,
    operationId: 'get_dashboard_me_dashboard_get',
    method: 'GET',
    schemaPath: '/me/dashboard',
    url: 'https://api.test/me/dashboard',
  })
}

describe('real-SDK envelope contracts', () => {
  beforeEach(() => {
    events.length = 0
    initRecordingTransport()
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(async () => {
    await Sentry.close()
    vi.restoreAllMocks()
    vi.unstubAllEnvs()
  })

  it('sends one upstream error envelope with bounded metadata and closed context', async () => {
    reportUpstreamFailure(undefined, {
      code: 'UPSTREAM_UNAVAILABLE',
      unsafe: SENTINEL_QUERY,
    })
    await Sentry.flush()

    expect(events).toHaveLength(1)
    const [event] = events
    expect(event.tags?.service).toBe('wren-web')
    expect(event.tags?.surface).toBe('web')
    expect(event.tags?.runtime).toBe('browser')
    expect(event.tags?.code).toBe('UPSTREAM_UNAVAILABLE')
    expect(event.tags?.unsafe).toBeUndefined()
    expect(event.tags?.['api.operation']).toBe('get_dashboard_me_dashboard_get')
    expect(event.tags?.['api.method']).toBe('GET')
    expect(event.tags?.['api.failure_kind']).toBe('upstream')
    expect(event.tags?.['api.domain']).toBe('accounts')
    expect(event.level).toBe('error')
    expect(event.release).toBe('wren-web@websha123')
    expect(event.contexts).toEqual({ report: { method: 'GET', status: 503 } })
  })

  it('sends one network warning envelope for a rejected request', async () => {
    reportApiFailure({
      error: new TypeError('offline'),
      status: null,
      operationId: 'get_dashboard_me_dashboard_get',
      method: 'GET',
      schemaPath: '/me/dashboard',
      url: 'https://api.test/me/dashboard',
    })
    await Sentry.flush()

    expect(events).toHaveLength(1)
    expect(events[0].level).toBe('warning')
    expect(events[0].tags?.['api.failure_kind']).toBe('network')
    expect(events[0].contexts).toEqual({ report: { method: 'GET', status: null } })
  })

  it('drops expected validation events before they reach the transport', async () => {
    reportApiFailure({
      status: 422,
      operationId: 'get_dashboard_me_dashboard_get',
      method: 'GET',
      schemaPath: '/me/dashboard',
      url: 'https://api.test/me/dashboard',
    })
    await Sentry.flush()

    expect(events).toHaveLength(0)
  })

  it('scrubs the serialized exception chain while preserving types and frames', async () => {
    const cause = new Error(SENTINEL_CAUSE + '?token=' + SENTINEL_QUERY)
    const error = new Error(SENTINEL_MSG)
    error.cause = cause

    reportUpstreamFailure(error)
    await Sentry.flush()

    expect(events).toHaveLength(1)
    const [event] = events
    const values = event.exception?.values ?? []
    expect(values.length).toBeGreaterThan(1)
    expect(values.map((value) => value.type)).toContain('Error')
    for (const value of values) {
      expect(value.value).toBe('[Redacted exception]')
      expect(value.mechanism).toBeUndefined()
      for (const frame of value.stacktrace?.frames ?? []) {
        expect(frame.vars).toBeUndefined()
      }
    }

    const serialized = JSON.stringify(event)
    expect(serialized).not.toContain(SENTINEL_QUERY)
    expect(serialized).not.toContain(SENTINEL_MSG)
    expect(serialized).not.toContain(SENTINEL_CAUSE)

    // The application error object is not mutated by reporting.
    expect(error.cause).toBe(cause)
  })

  it('deletes non-report contexts a stray scope might have added', async () => {
    Sentry.withScope((scope) => {
      scope.setContext('response', { url: 'https://api.test?token=' + SENTINEL_QUERY })
      scope.setContext('trace', { data: { secret: 'value' } })
      scope.setTag('unsafe', SENTINEL_QUERY)
      reportUpstreamFailure()
    })
    await Sentry.flush()

    expect(events).toHaveLength(1)
    expect(events[0].contexts).toEqual({ report: { method: 'GET', status: 503 } })
    expect(events[0].tags?.unsafe).toBeUndefined()
    expect(JSON.stringify(events[0])).not.toContain(SENTINEL_QUERY)
  })

})
