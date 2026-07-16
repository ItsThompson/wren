import { createContext, useContext, useMemo, type ReactNode } from 'react'

import { createSessionClient } from '@/auth/createSessionClient'

import { createApiClient, type ApiClient, type SessionClient } from '../client'

interface ApiClients {
  /** Credentialed client with the 401→refresh→retry middleware. */
  session: SessionClient
  /** Credential-free client for public reads. */
  public: ApiClient
}

const ApiClientContext = createContext<ApiClients | null>(null)

interface ApiClientProviderProps {
  baseUrl: string
  children: ReactNode
}

/**
 * Build exactly one session client and one public client per `baseUrl` and share
 * them via context. Memoized on `baseUrl`: an unchanged base reuses the instances
 * so `createSessionClient`'s in-flight refresh promise is shared across every
 * consumer (one refresh coalesces concurrent 401s); a changed base rebuilds both.
 */
export function ApiClientProvider({ baseUrl, children }: ApiClientProviderProps) {
  const clients = useMemo<ApiClients>(
    () => ({ session: createSessionClient(baseUrl), public: createApiClient(baseUrl) }),
    [baseUrl],
  )
  return <ApiClientContext.Provider value={clients}>{children}</ApiClientContext.Provider>
}

/** Access the shared session client. Throws if used outside an `ApiClientProvider`. */
export function useSessionClient(): SessionClient {
  const clients = useContext(ApiClientContext)
  if (clients === null) {
    throw new Error('useSessionClient must be used within an ApiClientProvider')
  }
  return clients.session
}

/** Access the shared public client. Throws if used outside an `ApiClientProvider`. */
export function usePublicClient(): ApiClient {
  const clients = useContext(ApiClientContext)
  if (clients === null) {
    throw new Error('usePublicClient must be used within an ApiClientProvider')
  }
  return clients.public
}
