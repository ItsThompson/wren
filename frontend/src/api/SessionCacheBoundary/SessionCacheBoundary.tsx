import { useRef, type ReactNode } from 'react'
import { SWRConfig, type Cache } from 'swr'

import { useAuth } from '@/auth'

interface SessionCacheBoundaryProps {
  children: ReactNode
  initialCache?: Cache
}

/** Isolate SWR data and in-flight requests for each resolved auth identity. */
export function SessionCacheBoundary({ children, initialCache }: SessionCacheBoundaryProps) {
  const { status, user } = useAuth()
  const resolvedIdentity = status === 'authenticated' && user ? `user:${user.id}` : status
  const initialIdentityRef = useRef<string | null>(null)
  const transitionedRef = useRef(false)
  if (status !== 'loading') {
    if (initialIdentityRef.current === null) {
      initialIdentityRef.current = resolvedIdentity
    } else if (initialIdentityRef.current !== resolvedIdentity) {
      transitionedRef.current = true
    }
  }
  const cacheIdentity = transitionedRef.current ? resolvedIdentity : 'stable'
  const initialCacheRef = useRef<Cache | undefined>(initialCache)
  const cacheForProvider = initialCacheRef.current
  initialCacheRef.current = undefined

  return (
    <SessionCacheProvider key={cacheIdentity} initialCache={cacheForProvider}>
      {children}
    </SessionCacheProvider>
  )
}

interface SessionCacheProviderProps {
  children: ReactNode
  initialCache?: Cache
}

function SessionCacheProvider({ children, initialCache }: SessionCacheProviderProps) {
  return <SWRConfig value={{ provider: () => initialCache ?? new Map() }}>{children}</SWRConfig>
}
