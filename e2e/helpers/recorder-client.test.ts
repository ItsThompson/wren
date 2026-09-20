import type { BrowserContext } from '@playwright/test'
import { describe, expect, it, vi } from 'vitest'

import {
  createRecorderQueryClient,
  installRecorderIngestionIdentity,
  pollForExactlyOneEnvelope,
} from './recorder-client'
import type { EnvelopeRecord } from '../recorder/src/types'

const record: EnvelopeRecord = {
  sequence: 1,
  receivedAtIso: '2026-09-19T00:00:00.000Z',
  queryIdentity: 'query-1',
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
  it('registers identity injection only for the recorder ingestion route', async () => {
    const route = vi.fn()
    await installRecorderIngestionIdentity(
      { route } as unknown as Pick<BrowserContext, 'route'>,
      'query-1',
    )

    expect(route).toHaveBeenCalledWith('**/_e2e/sentry/api/**', expect.any(Function))
  })

  it('uses the app ingress and keeps the raw response outside Playwright request tracing', async () => {
    const fetcher = vi.fn(async (input: string, init?: RequestInit) => {
      expect(new URL(input).origin).toBe('https://app.wren.test')
      expect(new URL(input).pathname).toBe('/_e2e/recorder/envelopes')
      const query = new URL(input).searchParams
      expect(query.get('operation')).toBe('get_dashboard_me_dashboard_get')
      expect(query.get('failureKind')).toBe('upstream')
      expect(query.get('receivedAfterIso')).toBe(record.receivedAtIso)
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

  it('rejects non-success recorder responses and invalid response payloads', async () => {
    const client = createRecorderQueryClient({
      fetcher: vi.fn(async () => response({ error: 'unauthorized' }, 401)),
    })
    await expect(client.query(record.operation!, 'upstream', record.receivedAtIso)).rejects.toThrow('status 401')

    const invalidJsonClient = createRecorderQueryClient({
      fetcher: vi.fn(async () => new Response('{', { status: 200 })),
    })
    await expect(
      invalidJsonClient.query(record.operation!, 'upstream', record.receivedAtIso),
    ).rejects.toThrow()

    const malformedPayloads: unknown[] = [
      {},
      { records: [{ ...record, sequence: Number.NaN }] },
      { records: [{ ...record, receivedAtIso: 'not-a-timestamp' }] },
      { records: [{ ...record, parseStatus: 'invalid' }] },
      { records: [{ ...record, status: 700 }] },
    ]
    for (const payload of malformedPayloads) {
      const malformedClient = createRecorderQueryClient({
        fetcher: vi.fn(async () => response(payload)),
      })
      await expect(
        malformedClient.query(record.operation!, 'upstream', record.receivedAtIso),
      ).rejects.toThrow(/invalid (response|record)/)
    }
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

  it('aborts a stalled recorder request before the polling deadline', async () => {
    const fetcher = vi.fn((_input: string, init?: RequestInit) => new Promise<Response>((_, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new Error('request aborted')), { once: true })
    }))
    const client = createRecorderQueryClient({ fetcher })

    await expect(
      pollForExactlyOneEnvelope(client, record.operation!, 'upstream', record.receivedAtIso, {
        timeoutMs: 30,
        requestTimeoutMs: 5,
        pollIntervalMs: 0,
      }),
    ).rejects.toThrow('timed out')
    expect(fetcher).toHaveBeenCalled()
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
