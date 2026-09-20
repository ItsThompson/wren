import { describe, expect, it } from 'vitest'

import {
  createAccountIdentity,
  createAttachmentIdentifier,
  createAttemptIdentity,
  createCallbackIdentity,
  createOAuthIdentity,
  createRecorderQueryIdentity,
  createRoadmapIdentity,
} from './attempt-identity.ts'

describe('attempt identity', () => {
  const input = {
    runId: 'run-123',
    projectName: 'chromium',
    file: '/workspace/e2e/tests/example.spec.ts',
    title: 'creates an attempt identity',
    parallelIndex: 3,
    retry: 1,
  }

  it('distinguishes identities created in the same timestamp window', () => {
    const first = createAttemptIdentity(input)
    const second = createAttemptIdentity(input)

    expect(first.runId).toBe(second.runId)
    expect(first.testId).toBe(second.testId)
    expect(first.resourcePrefix).not.toBe(second.resourcePrefix)
  })

  it('includes worker and retry dimensions in the resource identity', () => {
    const worker = createAttemptIdentity(input)
    const retry = createAttemptIdentity({ ...input, retry: 2 })
    const otherWorker = createAttemptIdentity({ ...input, parallelIndex: 4 })

    expect(worker.resourcePrefix).not.toBe(retry.resourcePrefix)
    expect(worker.resourcePrefix).not.toBe(otherWorker.resourcePrefix)
  })

  it('creates bounded product identifiers from one attempt identity', () => {
    const identity = createAttemptIdentity(input)
    const account = createAccountIdentity(identity, 'long-owner-role', 0)
    const roadmap = createRoadmapIdentity(identity)
    const oauth = createOAuthIdentity(identity, 0, 'http://127.0.0.1:43210/callback')
    const callback = createCallbackIdentity(identity)
    const recorder = createRecorderQueryIdentity(identity)
    const attachment = createAttachmentIdentifier(identity, 'trace.zip')

    expect(account.username).toMatch(/^[a-z0-9_-]{3,32}$/)
    expect(account.email).toMatch(/^[^@]+@example\.com$/)
    expect(account.email.length).toBeLessThanOrEqual(254)
    expect(roadmap.title.length).toBeLessThanOrEqual(120)
    expect(roadmap.proposedIdPrefix.length).toBeLessThanOrEqual(112)
    expect(roadmap.itemIds).toHaveLength(3)
    expect(new Set(roadmap.itemIds).size).toBe(3)
    expect(roadmap.itemIds.every((itemId) => itemId.length <= 120)).toBe(true)
    expect(oauth.clientName.length).toBeLessThanOrEqual(120)
    expect(oauth.redirectUri).toMatch(/^http:\/\/127\.0\.0\.1:\d+\/callback$/)
    expect(oauth.state).toContain(identity.resourcePrefix)
    expect(callback.length).toBeLessThanOrEqual(120)
    expect(recorder.length).toBeLessThanOrEqual(120)
    expect(attachment.length).toBeLessThanOrEqual(120)
  })
})
