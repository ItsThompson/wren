import { useCallback, useEffect, useRef, useState } from 'react'

import type { SessionClient } from '@/api'

import { toAuthResult } from '../api-errors'
import type { AuthResult, AuthStatus, AuthUser, LoginInput, RegisterInput } from '../types'

interface SessionState {
  status: AuthStatus
  user: AuthUser | null
}

const ANONYMOUS: SessionState = { status: 'anonymous', user: null }

/**
 * Owns the session: bootstraps from the current access session and only uses
 * the rotating refresh token when that access session is invalid. It exposes
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
  const sessionVersionRef = useRef(0)

  const bootstrap = useCallback(async () => {
    const bootstrapVersion = sessionVersionRef.current
    const isCurrent = () => sessionVersionRef.current === bootstrapVersion

    try {
      const { data, response } = await client.GET('/auth/session')
      if (!isCurrent()) return
      if (data) {
        setSession({ status: 'authenticated', user: data })
        return
      }
      if (response.status !== 401) {
        setSession(ANONYMOUS)
        return
      }

      const { data: refreshed } = await client.runAuthOperation(() => client.POST('/auth/refresh'))
      if (isCurrent()) {
        setSession(refreshed ? { status: 'authenticated', user: refreshed } : ANONYMOUS)
      }
    } catch {
      // No reachable backend or no usable session: resolve to anonymous rather
      // than hang in the loading state.
      if (isCurrent()) setSession(ANONYMOUS)
    }
  }, [client])

  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  const register = useCallback(
    async (input: RegisterInput): Promise<AuthResult> => {
      const requestVersion = ++sessionVersionRef.current
      const { data, error } = await client.runAuthOperation(() =>
        client.POST('/auth/register', { body: input }),
      )
      if (data) {
        if (requestVersion === sessionVersionRef.current) {
          setSession({ status: 'authenticated', user: data })
        }
        return { ok: true }
      }
      if (requestVersion === sessionVersionRef.current) setSession(ANONYMOUS)
      return toAuthResult(error)
    },
    [client],
  )

  const login = useCallback(
    async (input: LoginInput): Promise<AuthResult> => {
      const requestVersion = ++sessionVersionRef.current
      const { data, error } = await client.runAuthOperation(() =>
        client.POST('/auth/login', { body: input }),
      )
      if (data) {
        if (requestVersion === sessionVersionRef.current) {
          setSession({ status: 'authenticated', user: data })
        }
        return { ok: true }
      }
      if (requestVersion === sessionVersionRef.current) setSession(ANONYMOUS)
      return toAuthResult(error)
    },
    [client],
  )

  const applyUser = useCallback((user: AuthUser) => {
    // The caller already holds the authoritative updated user (e.g. the
    // onboarding completion response), so replace it directly rather than
    // re-fetching. Setting status keeps the impossible "authenticated with no
    // user" combination unrepresentable.
    sessionVersionRef.current += 1
    setSession({ status: 'authenticated', user })
  }, [])

  const logout = useCallback(async () => {
    const requestVersion = ++sessionVersionRef.current
    // Best-effort server revocation: clear the local session regardless of
    // whether the logout POST succeeds. Swallow any error so a failed POST
    // neither strands the user authenticated, surfaces as an unhandled
    // rejection, nor skips the caller's post-logout navigation.
    try {
      await client.runAuthOperation(() => client.POST('/auth/logout'))
    } catch {
      // Ignore: local sign-out below is the outcome that matters.
    }
    if (requestVersion === sessionVersionRef.current) setSession(ANONYMOUS)
  }, [client])

  return { ...session, register, login, logout, applyUser }
}
