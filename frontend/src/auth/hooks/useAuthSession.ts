import { useCallback, useEffect, useState } from 'react'

import type { SessionClient } from '@/api'

import { toAuthResult } from '../api-errors'
import type { AuthResult, AuthStatus, AuthUser, LoginInput, RegisterInput } from '../types'

interface SessionState {
  status: AuthStatus
  user: AuthUser | null
}

const ANONYMOUS: SessionState = { status: 'anonymous', user: null }

/**
 * Owns the session: resumes an existing session once on mount via the rotating
 * refresh token against the shared session client, and exposes
 * register/login/logout. State is a single `{status, user}` so the impossible
 * "authenticated with no user" combination cannot arise.
 */
export function useAuthSession(client: SessionClient): SessionState & {
  register: (input: RegisterInput) => Promise<AuthResult>
  login: (input: LoginInput) => Promise<AuthResult>
  logout: () => Promise<void>
  applyUser: (user: AuthUser) => void
} {
  const [session, setSession] = useState<SessionState>({ status: 'loading', user: null })

  const resume = useCallback(async () => {
    try {
      const { data } = await client.POST('/auth/refresh')
      setSession(data ? { status: 'authenticated', user: data } : ANONYMOUS)
    } catch {
      // No reachable backend / no session cookie: resolve to anonymous rather
      // than hang in the loading state.
      setSession(ANONYMOUS)
    }
  }, [client])

  useEffect(() => {
    void resume()
  }, [resume])

  const register = useCallback(
    async (input: RegisterInput): Promise<AuthResult> => {
      const { data, error } = await client.POST('/auth/register', { body: input })
      if (data) {
        setSession({ status: 'authenticated', user: data })
        return { ok: true }
      }
      return toAuthResult(error)
    },
    [client],
  )

  const login = useCallback(
    async (input: LoginInput): Promise<AuthResult> => {
      const { data, error } = await client.POST('/auth/login', { body: input })
      if (data) {
        setSession({ status: 'authenticated', user: data })
        return { ok: true }
      }
      return toAuthResult(error)
    },
    [client],
  )

  const applyUser = useCallback((user: AuthUser) => {
    // The caller already holds the authoritative updated user (e.g. the
    // onboarding completion response), so replace it directly rather than
    // re-fetching. Setting status keeps the impossible "authenticated with no
    // user" combination unrepresentable.
    setSession({ status: 'authenticated', user })
  }, [])

  const logout = useCallback(async () => {
    // Best-effort server revocation; the local session is cleared regardless of
    // whether the logout request succeeds. Swallow any error (rather than
    // try/finally, which re-propagates): a failed/rejected POST must neither
    // strand the user authenticated, nor surface as an unhandled rejection, nor
    // skip the caller's post-logout navigation.
    try {
      await client.POST('/auth/logout')
    } catch {
      // Ignore: local sign-out below is the outcome that matters.
    }
    setSession(ANONYMOUS)
  }, [client])

  return { ...session, register, login, logout, applyUser }
}
