import { describe, expect, it } from 'vitest'

import { MalformedEnvelopeError, parseSentryEnvelope } from './envelope-parser.ts'
import { makeEnvelope } from './test-fixtures.ts'

function envelopeText(event: string): Uint8Array {
  return new TextEncoder().encode(
    `${JSON.stringify({ event_id: 'event-1' })}\n${JSON.stringify({ type: 'event' })}\n${event}\n`,
  )
}

describe('parseSentryEnvelope', () => {
  it('extracts bounded recovery metadata from an event item', () => {
    expect(parseSentryEnvelope(makeEnvelope(), 'query-1')).toEqual({
      status: 'valid',
      queryIdentity: 'query-1',
      operation: 'get_dashboard_me_dashboard_get',
      failureKind: 'upstream',
      environment: 'production',
      service: 'wren-web',
      method: 'GET',
      responseStatus: 500,
    })
  })

  it('preserves null status for a network failure', () => {
    expect(parseSentryEnvelope(makeEnvelope({ failureKind: 'network', status: null }), 'query-1')).toMatchObject({
      queryIdentity: 'query-1',
      failureKind: 'network',
      responseStatus: null,
    })
  })

  it('accepts an envelope with an unsupported item without indexing event metadata', () => {
    const body = new TextEncoder().encode(
      `${JSON.stringify({ event_id: 'event-1' })}\n${JSON.stringify({ type: 'attachment' })}\nraw\n`,
    )
    expect(parseSentryEnvelope(body, 'query-1')).toEqual({
      status: 'unsupported',
      queryIdentity: 'query-1',
      operation: null,
      failureKind: null,
      environment: null,
      service: null,
      method: null,
      responseStatus: null,
    })
  })

  it('rejects malformed JSON and invalid UTF-8', () => {
    expect(() => parseSentryEnvelope(envelopeText('{'))).toThrow(MalformedEnvelopeError)
    expect(() => parseSentryEnvelope(new Uint8Array([0xff, 0xfe]))).toThrow(MalformedEnvelopeError)
  })
})
