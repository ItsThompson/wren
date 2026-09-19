import type { BrowserFailureKind } from './types.ts'

export function makeEnvelope(options: {
  operation?: string
  failureKind?: BrowserFailureKind
  environment?: string
  service?: string
  method?: string
  status?: number | null
} = {}): Uint8Array {
  const event = {
    environment: options.environment ?? 'production',
    tags: {
      service: options.service ?? 'wren-web',
      'api.operation': options.operation ?? 'get_dashboard_me_dashboard_get',
      'api.failure_kind': options.failureKind ?? 'upstream',
    },
    contexts: {
      report: {
        method: options.method ?? 'GET',
        status: options.status === undefined ? 500 : options.status,
      },
    },
    exception: { values: [{ value: '[Redacted exception]' }] },
  }
  const lines = [
    JSON.stringify({ event_id: 'event-1' }),
    JSON.stringify({ type: 'event' }),
    JSON.stringify(event),
  ]
  return new TextEncoder().encode(`${lines.join('\n')}\n`)
}
