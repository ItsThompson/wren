import * as Sentry from '@sentry/react'

import { scrubSentryEvent } from './scrub'

export function beforeSendSentryEvent<T extends Sentry.Event>(event: T): T | null {
  if (event.tags?.expected === 'true') return null
  return scrubSentryEvent(event)
}

export function initSentry(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN?.trim()
  if (!dsn) return

  Sentry.init({
    dsn,
    environment: import.meta.env.MODE,
    release: import.meta.env.VITE_SENTRY_RELEASE,
    sendDefaultPii: false,
    defaultIntegrations: [],
    integrations: [],
    enableLogs: false,
    maxBreadcrumbs: 0,
    tracesSampleRate: 0,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
    beforeSend: beforeSendSentryEvent,
  })
}
