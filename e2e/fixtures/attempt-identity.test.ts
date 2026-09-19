import { describe, expect, it } from 'vitest'

import {
  createAccountIdentity,
  createAttachmentIdentifier,
  createAttemptIdentity,
  createCallbackIdentity,
  createOAuthClientName,
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

    expect(account.username).toMatch(/^[a-z0-9_-]{3,32}$/)
    expect(account.email).toBe(`${account.username}@example.com`)
    expect(roadmap.title).toContain(identity.resourcePrefix)
    expect(createOAuthClientName(identity)).toContain(identity.resourcePrefix)
    expect(createAttachmentIdentifier(identity, 'trace.zip')).toContain(identity.resourcePrefix)
    expect(createCallbackIdentity(identity)).toContain(identity.resourcePrefix)
    expect(createRecorderQueryIdentity(identity)).toContain(identity.resourcePrefix)
  })
})
