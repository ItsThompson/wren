import type { components } from '@/api'

/** The authenticated user's own view (generated from the backend OpenAPI). */
export type AuthUser = components['schemas']['AuthenticatedUser']

/** Resolved session status. `loading` covers the initial resume-on-mount probe. */
export type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

export interface RegisterInput {
  username: string
  email: string
  password: string
}

export interface LoginInput {
  email: string
  password: string
}

/**
 * Outcome of a register/login attempt. Success flips the provider to
 * authenticated; failure carries a human message plus any RFC 9457 field-level
 * errors so the form can attach them to the offending input.
 */
export type AuthResult =
  | { ok: true }
  | { ok: false; message: string; fields?: Record<string, string> }

export interface AuthContextValue {
  status: AuthStatus
  user: AuthUser | null
  register: (input: RegisterInput) => Promise<AuthResult>
  login: (input: LoginInput) => Promise<AuthResult>
  logout: () => Promise<void>
  /**
   * Replace the current session user, marking the session authenticated. The
   * onboarding wizard uses this to push the completion endpoint's fresh
   * `AuthenticatedUser` (flag now `true`) into context *before* it navigates, so
   * the route guard sees the updated flag and does not bounce the user back.
   */
  applyUser: (user: AuthUser) => void
}
