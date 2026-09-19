import { describe, expect, it, vi } from 'vitest'

import {
  createRecorderQueryClient,
  pollForExactlyOneEnvelope,
} from './recorder-client'
import type { EnvelopeRecord } from '../recorder/src/types'

const record: EnvelopeRecord = {
  sequence: 1,
  receivedAtIso: '2026-09-19T00:00:00.000Z',
  rawEnvelopeUtf8: 'raw-envelope',
  parseStatus: 'valid',
  operation: 'get_dashboard_me_dashboard_get',
  failureKind: 'upstream',
  environment: 'production',
  service: 'wren-web',
  method: 'GET',
  status: 500,
}

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

describe('recorder query client', () => {
  it('uses the app ingress and keeps the raw response outside Playwright request tracing', async () => {
    const fetcher = vi.fn(async (input: string, init?: RequestInit) => {
      expect(new URL(input).origin).toBe('https://app.wren.test')
      expect(new URL(input).pathname).toBe('/_e2e/recorder/envelopes')
      expect(new URL(input).searchParams.get('operation')).toBe('get_dashboard_me_dashboard_get')
      expect(init?.headers).toEqual({
        'X-Recorder-Token': 'control-token',
        'X-Recorder-Query-Identity': 'query-1',
      })
      return response({ records: [record] })
    })
    const client = createRecorderQueryClient({
      controlToken: 'control-token',
      queryIdentity: 'query-1',
      fetcher,
    })

    await expect(client.query('get_dashboard_me_dashboard_get', 'upstream', record.receivedAtIso)).resolves.toEqual([record])
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('waits for one record and rejects duplicate matches', async () => {
    const query = vi.fn()
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([record])
    const client = { query }

    await expect(
      pollForExactlyOneEnvelope(client, record.operation!, 'upstream', record.receivedAtIso, {
        timeoutMs: 100,
        pollIntervalMs: 0,
      }),
    ).resolves.toEqual(record)

    await expect(
      pollForExactlyOneEnvelope(
        { query: vi.fn().mockResolvedValue([record, { ...record, sequence: 2 }]) },
        record.operation!,
        'upstream',
        record.receivedAtIso,
        { timeoutMs: 100, pollIntervalMs: 0 },
      ),
    ).rejects.toThrow('duplicate')
  })

  it('fails with safe query metadata when no record arrives', async () => {
    const client = { query: vi.fn().mockResolvedValue([]) }

    await expect(
      pollForExactlyOneEnvelope(client, record.operation!, 'upstream', record.receivedAtIso, {
        timeoutMs: 0,
        pollIntervalMs: 0,
      }),
    ).rejects.toThrow('get_dashboard_me_dashboard_get/upstream')
  })
})
