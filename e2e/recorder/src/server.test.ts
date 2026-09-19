import { afterEach, describe, expect, it } from 'vitest'
import type { AddressInfo } from 'node:net'

import { EnvelopeStore } from './envelope-store.ts'
import { createRecorderServer, type RecorderServer } from './server.ts'
import { makeEnvelope } from './test-fixtures.ts'

const token = 'job-control-token'
const receivedAt = new Date('2026-09-19T00:00:00.000Z')
const servers: RecorderServer[] = []

async function startServer(
  store = new EnvelopeStore({}, () => receivedAt),
  limits?: { maxEnvelopeBytes?: number },
): Promise<string> {
  const recorder = createRecorderServer({ controlToken: token, store, limits })
  servers.push(recorder)
  await new Promise<void>((resolve) => recorder.server.listen(0, '127.0.0.1', resolve))
  const address = recorder.server.address() as AddressInfo
  return `http://127.0.0.1:${address.port}`
}

async function jsonResponse(response: Response): Promise<Record<string, unknown>> {
  return (await response.json()) as Record<string, unknown>
}

afterEach(async () => {
  await Promise.all(servers.splice(0).map((recorder) => new Promise<void>((resolve, reject) => {
    recorder.server.close((error) => error ? reject(error) : resolve())
  })))
})

describe('recorder HTTP boundary', () => {
  it('requires the control token on every control route', async () => {
    const baseUrl = await startServer()
    const controlPaths = [
      '/_e2e/recorder/ready',
      '/_e2e/recorder/envelopes',
      '/_e2e/recorder/artifacts',
    ]
    for (const controlPath of controlPaths) {
      const unauthorized = await fetch(`${baseUrl}${controlPath}`)
      expect(unauthorized.status).toBe(401)
    }

    const authorized = await fetch(`${baseUrl}/_e2e/recorder/ready`, {
      headers: { 'X-Recorder-Token': token },
    })
    expect(authorized.status).toBe(200)
    expect(await jsonResponse(authorized)).toEqual({ ready: true, parser: 'ready', store: 'ready' })
  })

  it('accepts the path-prefixed envelope and returns bounded query content', async () => {
    const baseUrl = await startServer()
    const body = makeEnvelope()
    const ingested = await fetch(`${baseUrl}/_e2e/sentry/api/1/envelope/`, {
      method: 'POST',
      body: Buffer.from(body),
      headers: { 'Content-Type': 'application/x-sentry-envelope' },
    })
    expect(ingested.status).toBe(200)

    const query = await fetch(
      `${baseUrl}/_e2e/recorder/envelopes?operation=get_dashboard_me_dashboard_get&failureKind=upstream&receivedAfterIso=2026-09-18T23%3A59%3A59.999Z`,
      { headers: { 'X-Recorder-Token': token } },
    )
    expect(query.status).toBe(200)
    const payload = await jsonResponse(query)
    const records = payload.records as Array<Record<string, unknown>>
    expect(records).toHaveLength(1)
    expect(records[0]).toMatchObject({ sequence: 1, operation: 'get_dashboard_me_dashboard_get' })
    expect(records[0]?.rawEnvelopeUtf8).toEqual(expect.stringContaining('event-1'))

    const artifacts = await fetch(`${baseUrl}/_e2e/recorder/artifacts`, {
      headers: { 'X-Recorder-Token': token },
    })
    const artifactPayload = await jsonResponse(artifacts)
    expect(artifactPayload.records).toEqual([{
      sequence: 1,
      receivedAtIso: receivedAt.toISOString(),
      operation: 'get_dashboard_me_dashboard_get',
      failureKind: 'upstream',
      environment: 'production',
      service: 'wren-web',
      method: 'GET',
      status: 500,
    }])
  })

  it('rejects malformed and oversized envelopes without indexing them', async () => {
    const store = new EnvelopeStore({ maxEnvelopeBytes: 32 }, () => receivedAt)
    const baseUrl = await startServer(store, { maxEnvelopeBytes: 32 })
    const malformed = await fetch(`${baseUrl}/_e2e/sentry/api/1/envelope/`, {
      method: 'POST',
      body: new TextEncoder().encode('{}'),
    })
    expect(malformed.status).toBe(400)

    const oversized = await fetch(`${baseUrl}/_e2e/sentry/api/1/envelope/`, {
      method: 'POST',
      body: Buffer.alloc(33),
    })
    expect(oversized.status).toBe(413)
    expect(store.exportArtifacts()).toEqual([])
  })

  it('rejects invalid bounded queries and unknown ingestion paths', async () => {
    const baseUrl = await startServer()
    const invalidQuery = await fetch(`${baseUrl}/_e2e/recorder/envelopes?operation=x&failureKind=bad&receivedAfterIso=2026-09-18T23%3A59%3A59.999Z`, {
      headers: { 'X-Recorder-Token': token },
    })
    expect(invalidQuery.status).toBe(400)

    const unknownPath = await fetch(`${baseUrl}/_e2e/sentry/api/2/store/`, {
      method: 'POST',
      body: Buffer.from(makeEnvelope()),
    })
    expect(unknownPath.status).toBe(404)

  })
})
