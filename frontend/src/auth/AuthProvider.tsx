import type { ReactNode } from 'react'

import { AuthContext } from './auth-context'
import { useAuthSession } from './hooks/useAuthSession'

/**
 * Same-origin by default (dev proxy + MSW); prod points at the API subdomain via
 * `VITE_API_BASE_URL`. Read once at module load: the deployment base never
 * changes at runtime.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

interface AuthProviderProps {
  children: ReactNode
  /** Overridable in tests; defaults to the deployment API base URL. */
  baseUrl?: string
}

/**
 * Owns the session and transparent refresh, and publishes
 * `status`/`user` plus the register/login/logout actions to the tree via context.
 */
export function AuthProvider({ children, baseUrl = API_BASE_URL }: AuthProviderProps) {
  const value = useAuthSession(baseUrl)
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
