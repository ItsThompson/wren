import { describe, expect, it } from 'vitest'

import { parseSentryEnvelope } from './envelope-parser.ts'
import { EnvelopeStore, RecorderStorageLimitError, RecorderValidationError } from './envelope-store.ts'
import { makeEnvelope } from './test-fixtures.ts'

const receivedAt = new Date('2026-09-19T00:00:00.000Z')

function appendEnvelope(store: EnvelopeStore, options: Parameters<typeof makeEnvelope>[0] = {}): void {
  const body = makeEnvelope(options)
  store.append(body, parseSentryEnvelope(body))
}

describe('EnvelopeStore', () => {
  it('assigns monotonic sequences and keeps records append-only', () => {
    const store = new EnvelopeStore({}, () => receivedAt)
    appendEnvelope(store)
    appendEnvelope(store, { failureKind: 'network', status: null })

    const records = store.query({
      operation: 'get_dashboard_me_dashboard_get',
      failureKind: 'upstream',
      receivedAfterIso: receivedAt.toISOString(),
    })
    expect(records).toHaveLength(1)
    expect(records[0]?.sequence).toBe(1)
    expect(records[0]?.rawEnvelopeUtf8).toContain('event-1')
    expect(store.exportArtifacts()).toHaveLength(2)
  })

  it('assigns unique sequences when appends are concurrent', async () => {
    const store = new EnvelopeStore({}, () => receivedAt)
    await Promise.all(Array.from({ length: 50 }, () => Promise.resolve().then(() => appendEnvelope(store))))

    const artifacts = store.exportArtifacts()
    expect(artifacts.map((artifact) => artifact.sequence)).toEqual(
      Array.from({ length: 50 }, (_, index) => index + 1),
    )
  })

  it('bounds and validates control queries', () => {
    const store = new EnvelopeStore({ maxQueryResults: 2 }, () => receivedAt)
    appendEnvelope(store)
    appendEnvelope(store)
    appendEnvelope(store)

    expect(() => store.query({
      operation: '',
      failureKind: 'upstream',
      receivedAfterIso: '2026-09-18T23:59:59.999Z',
    })).toThrow(RecorderValidationError)
    expect(() => store.query({
      operation: 'get_dashboard_me_dashboard_get',
      failureKind: 'upstream',
      receivedAfterIso: 'not-a-time',
      limit: 3,
    })).toThrow(RecorderValidationError)
    expect(store.query({
      operation: 'get_dashboard_me_dashboard_get',
      failureKind: 'upstream',
      receivedAfterIso: receivedAt.toISOString(),
      limit: 2,
    })).toHaveLength(2)
  })

  it('rejects storage overflow without deleting existing records', () => {
    const store = new EnvelopeStore({ maxStoredBytes: makeEnvelope().byteLength + 1 }, () => receivedAt)
    appendEnvelope(store)
    expect(() => appendEnvelope(store)).toThrow(RecorderStorageLimitError)
    expect(store.exportArtifacts()).toHaveLength(1)
  })

  it('exports only the safe allowlist and excludes incomplete records', () => {
    const store = new EnvelopeStore({}, () => receivedAt)
    const complete = makeEnvelope()
    store.append(complete, parseSentryEnvelope(complete))
    const incomplete = makeEnvelope({ operation: undefined })
    store.append(incomplete, {
      ...parseSentryEnvelope(incomplete),
      service: null,
    })

    expect(store.exportArtifacts()).toEqual([{
      sequence: 1,
      receivedAtIso: receivedAt.toISOString(),
      operation: 'get_dashboard_me_dashboard_get',
      failureKind: 'upstream',
      environment: 'production',
      service: 'wren-web',
      method: 'GET',
      status: 500,
    }])
    expect(Object.keys(store.exportArtifacts()[0] ?? {}).sort()).toEqual([
      'environment',
      'failureKind',
      'method',
      'operation',
      'receivedAtIso',
      'sequence',
      'service',
      'status',
    ])
  })
})
