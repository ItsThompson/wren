import type { ReactNode } from 'react'

import { useSessionClient } from '@/api'

import { AuthContext } from './auth-context'
import { useAuthSession } from './hooks/useAuthSession'

interface AuthProviderProps {
  children: ReactNode
}

/**
 * Owns the session and transparent refresh, and publishes
 * `status`/`user` plus the register/login/logout actions to the tree via context.
 * Consumes the shared session client from `ApiClientProvider`, so every hook in
 * the tree drives the same 401→refresh→retry lock.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const client = useSessionClient()
  const value = useAuthSession(client)
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
