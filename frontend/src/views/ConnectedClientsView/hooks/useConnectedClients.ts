import { useCallback } from 'react'
import { useSWRConfig } from 'swr'

import { keys, useApiQuery, useSessionClient } from '@/api'
import type { Problem } from '@/lib/problem'

import type { ClientsListState, ConnectedClient } from '../types'

/**
 * Derive the view's semantic phase-state from the SWR read result. Any failure
 * (including a network failure, where `Problem.status` is `null`) is the generic
 * `error`: the list has no first-class per-status branch. The loading guard
 * holds only while there is no cached `data`, so a background revalidation keeps
 * the last-loaded list on screen instead of flashing the skeleton.
 */
function toClientsListState(
  data: ConnectedClient[] | undefined,
  error: Problem | undefined,
  isLoading: boolean,
): ClientsListState {
  if (isLoading && !data) return { phase: 'loading' }
  if (error) return { phase: 'error' }
  if (data) return { phase: 'loaded', clients: data }
  return { phase: 'loading' }
}

/**
 * Owns the connected-clients surface (`/me/clients`): it lists the signed-in
 * user's authorized agents and revokes one (RFC 7009). Reads through
 * {@link useApiQuery} so it binds the shared session client (credentials +
 * transparent refresh) from context; the backend scopes every call to the
 * caller's own grants, so the action is inherently limited to the user's own
 * clients.
 *
 * Fetching is gated on `enabled` via a null key: the caller enables it only once
 * the session resolves to authenticated, and a `null` key never fetches (no
 * request, no loading churn). `reload` revalidates the cache entry via `mutate()`
 * for the inline error-retry.
 *
 * `revoke` stays imperative (a direct `DELETE`); on success it removes the row
 * from the `keys.clients()` cache entry with `{ revalidate: false }` so any
 * co-mounted reader stays coherent without an extra GET (the backend has already
 * invalidated the grant). A failed revoke leaves the row in place and returns
 * `false`.
 */
export function useConnectedClients(enabled: boolean): {
  state: ClientsListState
  revoke: (clientId: string) => Promise<boolean>
  reload: () => void
} {
  const client = useSessionClient()
  const { mutate: mutateKey } = useSWRConfig()
  const { data, error, isLoading, mutate } = useApiQuery(enabled ? keys.clients() : null, (c) =>
    c.GET('/me/clients'),
  )

  const revoke = useCallback(
    async (clientId: string): Promise<boolean> => {
      try {
        const { error: deleteError, response } = await client.DELETE('/me/clients/{client_id}', {
          params: { path: { client_id: clientId } },
        })
        if (deleteError || !response.ok) return false
        await mutateKey<ConnectedClient[]>(
          keys.clients(),
          (list) => (list ?? []).filter((entry) => entry.client_id !== clientId),
          { revalidate: false },
        )
        return true
      } catch {
        return false
      }
    },
    [client, mutateKey],
  )

  return {
    state: toClientsListState(data, error, isLoading),
    revoke,
    reload: () => {
      void mutate()
    },
  }
}
