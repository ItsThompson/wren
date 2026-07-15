import { useCallback, useEffect, useMemo, useState } from 'react'

import { toAuthResult } from '../api-errors'
import { createSessionClient } from '../createSessionClient'
import type { AuthResult, AuthStatus, AuthUser, LoginInput, RegisterInput } from '../types'

interface SessionState {
  status: AuthStatus
  user: AuthUser | null
}

const ANONYMOUS: SessionState = { status: 'anonymous', user: null }

/**
 * Owns the session (section 10): builds the session client, resumes an existing
 * session once on mount via the rotating refresh token, and exposes
 * register/login/logout. State is a single `{status, user}` so the impossible
 * "authenticated with no user" combination cannot arise.
 */
export function useAuthSession(baseUrl: string): SessionState & {
  register: (input: RegisterInput) => Promise<AuthResult>
  login: (input: LoginInput) => Promise<AuthResult>
  logout: () => Promise<void>
} {
  const client = useMemo(() => createSessionClient(baseUrl), [baseUrl])
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

  const logout = useCallback(async () => {
    // Best-effort server revocation; the client session is cleared regardless.
    await client.POST('/auth/logout')
    setSession(ANONYMOUS)
  }, [client])

  return { ...session, register, login, logout }
}
