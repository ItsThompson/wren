import { describe, expect, it } from 'vitest'

import { InMemorySensitiveValueRegistry } from '../fixtures/sensitive-value-registry'
import type { EnvelopeRecord } from '../recorder/src/types'
import { assertPrivateEnvelope } from './envelope-privacy'

function buildRecord(
  event: Record<string, unknown>,
  additionalEvents: readonly Record<string, unknown>[] = [],
): EnvelopeRecord {
  const items = [event, ...additionalEvents]
  const rawEnvelopeLines = [JSON.stringify({})]
  for (const item of items) {
    rawEnvelopeLines.push(JSON.stringify({ type: 'event' }), JSON.stringify(item))
  }
  return {
    sequence: 1,
    receivedAtIso: '2026-01-01T00:00:00.000Z',
    queryIdentity: 'query-1',
    rawEnvelopeUtf8: `${rawEnvelopeLines.join('\n')}\n`,
    parseStatus: 'valid',
    operation: 'operation',
    failureKind: 'upstream',
    environment: 'production',
    service: 'wren-web',
    method: 'GET',
    status: 500,
  }
}

describe('envelope privacy assertions', () => {
  it('accepts a scrubbed event with the expected report context', () => {
    const registry = new InMemorySensitiveValueRegistry()
    registry.register('password', 'secret-password')

    expect(() => assertPrivateEnvelope(
      buildRecord({ contexts: { report: { method: 'GET', status: 500 } } }),
      500,
      registry,
    )).not.toThrow()
  })

  it('rejects malformed and non-JSON envelope content safely', () => {
    const registry = new InMemorySensitiveValueRegistry()
    const malformedPayload = {
      ...buildRecord({ contexts: { report: { method: 'GET', status: 500 } } }),
      rawEnvelopeUtf8: '{}\n{"type":"event"}\nnot-json\n',
    }
    expect(() => assertPrivateEnvelope(malformedPayload, 500, registry)).toThrow(
      'recorder returned a non-JSON envelope payload',
    )

    const malformedHeader = {
      ...buildRecord({ contexts: { report: { method: 'GET', status: 500 } } }),
      rawEnvelopeUtf8: '{}\nnot-json\n{}\n',
    }
    expect(() => assertPrivateEnvelope(malformedHeader, 500, registry)).toThrow(
      'recorder returned a non-JSON envelope item header',
    )
  })

  it('rejects forbidden fields in later envelope items', () => {
    const registry = new InMemorySensitiveValueRegistry()
    const record = buildRecord(
      { contexts: { report: { method: 'GET', status: 500 } } },
      [{ breadcrumbs: [{ message: 'later event' }] }],
    )

    expect(() => assertPrivateEnvelope(record, 500, registry)).toThrow(
      'privacy check failed: forbidden event key breadcrumbs',
    )
  })

  it('keeps privacy failure diagnostics free of raw payloads and sensitive values', () => {
    const sensitiveValue = 'secret-password'
    const event = {
      contexts: { report: { method: 'GET', status: 500 } },
      password: sensitiveValue,
    }
    const rawEnvelope = JSON.stringify(event)
    const registry = new InMemorySensitiveValueRegistry()
    registry.register('password', sensitiveValue)
    const record = buildRecord(event)

    let diagnostic = ''
    try {
      assertPrivateEnvelope(record, 500, registry)
    } catch (error: unknown) {
      diagnostic = error instanceof Error ? error.message : String(error)
    }

    expect(diagnostic).toBe('privacy check failed: forbidden event key password')
    expect(diagnostic).not.toContain(rawEnvelope)
    expect(diagnostic).not.toContain(sensitiveValue)
    expect(diagnostic).not.toContain(record.rawEnvelopeUtf8)
  })
})
