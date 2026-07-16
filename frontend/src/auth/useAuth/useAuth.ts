import { useContext } from 'react'

import { AuthContext } from '../auth-context'
import type { AuthContextValue } from '../types'

/** Read the session context. Throws if used outside an `AuthProvider`. */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (context === null) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
