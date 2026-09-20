import type { APIRequestContext } from '@playwright/test'
import { describe, expect, it, vi } from 'vitest'

import {
  createAttemptIdentity,
  createAttemptResourceIdentities,
} from './attempt-identity.ts'
import { createCallbackListener } from './callback-listener.ts'
import { OwnedContextResources } from './context-owner.ts'
import { createRecorderClient, type RecorderClient } from './recorder-client.ts'

interface WorkerSession {
  owner: OwnedContextResources
  callbackUrl: string
  callbackIdentity: string
  recorderIdentity: string
  callback: Promise<URL>
  query: ReturnType<typeof vi.fn>
  dispose: ReturnType<typeof vi.fn>
  recorderClient: RecorderClient
  newContext: ReturnType<typeof vi.fn>
}

async function createWorkerSession(parallelIndex: number): Promise<WorkerSession> {
  const attemptIdentity = createAttemptIdentity({
    runId: 'shared-run',
    projectName: 'chromium',
    file: 'fixture-harness.spec.ts',
    title: 'two worker callback recorder ownership',
    parallelIndex,
    retry: 0,
    nonce: 'parallel-test',
  })
  const identities = createAttemptResourceIdentities(attemptIdentity)
  const owner = new OwnedContextResources()
  const callbackListener = await createCallbackListener(attemptIdentity, owner)
  const dispose = vi.fn(async () => undefined)
  const query = vi.fn(async () => ({
    ok: () => true,
    status: () => 200,
    json: async () => ({ records: [] }),
  }))
  const context = {
    get: query,
    dispose,
  } as unknown as APIRequestContext
  const newContext = vi.fn(async () => context)
  const request = { newContext }
  const recorderClient = await createRecorderClient(
    request,
    owner,
    identities.recorder(),
  )

  return {
    owner,
    callbackUrl: callbackListener.callbackUrl,
    callbackIdentity: callbackListener.callbackIdentity,
    recorderIdentity: recorderClient.queryIdentity,
    callback: callbackListener.waitForCallback(),
    query,
    dispose,
    recorderClient,
    newContext,
  }
}

describe('callback and recorder fixture ownership', () => {
  it('keeps two worker sessions independent and closes both resource sets', async () => {
    const sessions = await Promise.all([createWorkerSession(0), createWorkerSession(1)])

    expect(sessions[0].callbackUrl).not.toBe(sessions[1].callbackUrl)
    expect(sessions[0].newContext).toHaveBeenCalledWith({ baseURL: 'https://app.wren.test' })
    expect(sessions[1].newContext).toHaveBeenCalledWith({ baseURL: 'https://app.wren.test' })
    expect(sessions[0].callbackIdentity).not.toBe(sessions[1].callbackIdentity)
    expect(sessions[0].recorderIdentity).not.toBe(sessions[1].recorderIdentity)

    await Promise.all(sessions.map(async (session) => {
      await fetch(`${session.callbackUrl}?code=worker-code`)
      await session.callback
      await session.recorderClient.query(
        'list_clients_me_clients_get',
        'network',
        '2026-09-19T00:00:00.000Z',
      )
    }))

    expect(sessions[0].query).toHaveBeenCalledWith(
      '/_e2e/recorder/envelopes',
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-Recorder-Query-Identity': sessions[0].recorderIdentity,
        }),
      }),
    )
    await Promise.all(sessions.map((session) => session.owner.closeAll()))
    expect(sessions.every((session) => session.dispose.mock.calls.length === 1)).toBe(true)
  })
})
