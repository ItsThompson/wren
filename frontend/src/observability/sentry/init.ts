import * as Sentry from '@sentry/react'

import { scrubSentryEvent } from './scrub'

export function initSentry(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN?.trim()
  if (!dsn) return

  Sentry.init({
    dsn,
    environment: import.meta.env.MODE,
    release: import.meta.env.VITE_SENTRY_RELEASE,
    sendDefaultPii: false,
    beforeSend: scrubSentryEvent,
  })
}
