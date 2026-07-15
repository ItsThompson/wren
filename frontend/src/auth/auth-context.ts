import { createContext } from 'react'

import type { AuthContextValue } from './types'

/**
 * Session context. `null` until an `AuthProvider` mounts; `useAuth` turns that
 * into a clear error rather than silently returning a broken value.
 */
export const AuthContext = createContext<AuthContextValue | null>(null)
