export interface TestUser {
  username: string
  email: string
  password: string
}

let sequence = 0

/**
 * A fresh, unique user per call so the suite's per-test users never collide
 * (spec section 13: "per-test unique users"). The handle is lowercase
 * alphanumeric to satisfy username validation; the email derives from it so it
 * is unique too.
 */
export function uniqueUser(role = 'user'): TestUser {
  sequence += 1
  const token = `${Date.now().toString(36)}${sequence}${Math.random().toString(36).slice(2, 8)}`
  const handle = `e2e${role}${token}`.toLowerCase().replace(/[^a-z0-9]/g, '')
  return {
    username: handle,
    email: `${handle}@example.test`,
    password: 'Str0ngPass1',
  }
}
