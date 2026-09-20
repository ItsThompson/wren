import { randomBytes } from 'node:crypto'

import type { TestAttemptIdentity } from '../fixtures/attempt-identity'
import { createAccountIdentity } from '../fixtures/attempt-identity'

export interface TestUser {
  username: string
  email: string
  password: string
}

/** Create a standalone test user when a fixture identity is not available. */
export function uniqueUser(role = 'user', identity?: TestAttemptIdentity): TestUser {
  if (identity !== undefined) return createAccountIdentity(identity, role, 0)
  const handle = `e2e${role}${randomBytes(8).toString('hex')}`.toLowerCase().replace(/[^a-z0-9]/g, '')
  const username = handle.slice(0, 32)
  return {
    username,
    email: `${username}@example.com`,
    password: 'Str0ngPass1',
  }
}
