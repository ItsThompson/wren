import type { Event } from '@sentry/react'

/**
 * Minimal structural shape of a Sentry wire envelope: `[headers, items]` where
 * an event item is `[itemHeaders, Event]`. The SDK's own `Envelope` type is not
 * exported from `@sentry/react`, so tests describe only what they read.
 */
export type RecordedEventEnvelope = [
  Record<string, unknown>,
  Array<[Record<string, unknown>, unknown]>,
]

/**
 * Transport factory for real-SDK tests: records every post-`beforeSend` event
 * instead of sending anything over the network.
 */
export function makeRecordingTransport(events: Event[]): () => {
  send: (envelope: RecordedEventEnvelope) => Promise<Record<string, never>>
  flush: () => Promise<boolean>
} {
  return () => ({
    send: (envelope: RecordedEventEnvelope) => {
      for (const item of envelope[1] ?? []) {
        if (item[0].type === 'event') {
          events.push(item[1] as Event)
        }
      }
      return Promise.resolve({})
    },
    flush: () => Promise.resolve(true),
  })
}

export const TEST_SENTRY_DSN = 'https://testingkey@o0.ingest.sentry.io/1'
