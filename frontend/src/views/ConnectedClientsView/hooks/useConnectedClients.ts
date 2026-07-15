import { useCallback, useEffect, useMemo, useState } from 'react'

import { createSessionClient } from '@/auth/createSessionClient'
import type { ClientsListState } from '../types'

/**
 * Owns the connected-clients surface (`/me/clients`): it lists the
 * signed-in user's authorized agents and revokes one (RFC 7009). The
 * session-aware client scopes every call to the caller's own grants, so the
 * action is inherently limited to the user's own clients.
 *
 * Fetching is gated on `enabled` (the caller only enables it once the session
 * resolves to authenticated). A successful revoke removes the row locally rather
 * than refetching, since the backend has already invalidated the grant. `reload`
 * re-runs the fetch for the inline error-retry.
 *
 * `baseUrl` is injected (defaulted at the view) so tests can point at an MSW
 * server without touching global config.
 */
export function useConnectedClients(
  baseUrl: string,
  enabled: boolean,
): {
  state: ClientsListState
  revoke: (clientId: string) => Promise<boolean>
  reload: () => void
} {
  const client = useMemo(() => createSessionClient(baseUrl), [baseUrl])
  const [state, setState] = useState<ClientsListState>({ phase: 'loading' })
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    if (!enabled) return
    let active = true
    setState({ phase: 'loading' })

    void (async () => {
      try {
        const { data } = await client.GET('/me/clients')
        if (!active) return
        setState(data ? { phase: 'loaded', clients: data } : { phase: 'error' })
      } catch {
        if (active) setState({ phase: 'error' })
      }
    })()

    return () => {
      active = false
    }
  }, [client, enabled, reloadToken])

  const revoke = useCallback(
    async (clientId: string): Promise<boolean> => {
      try {
        const { error, response } = await client.DELETE('/me/clients/{client_id}', {
          params: { path: { client_id: clientId } },
        })
        if (error || !response.ok) return false
        setState((prev) =>
          prev.phase === 'loaded'
            ? {
                phase: 'loaded',
                clients: prev.clients.filter((entry) => entry.client_id !== clientId),
              }
            : prev,
        )
        return true
      } catch {
        return false
      }
    },
    [client],
  )

  const reload = useCallback(() => setReloadToken((token) => token + 1), [])

  return { state, revoke, reload }
}
