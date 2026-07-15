import { useCallback, useEffect, useMemo, useState } from 'react'

import { createSessionClient } from '@/auth/createSessionClient'
import type { DashboardState } from '../types'

/**
 * Owns the private dashboard fetch (`GET /me/dashboard`):
 * the caller's authored roadmaps (any status) plus the ones they follow. Uses the
 * session-aware client (credentials + transparent refresh), so the backend scopes
 * the response to the resolved session user; another user's dashboard is never
 * returned.
 *
 * Fetching is gated on `enabled` (the caller enables it only once the session
 * resolves to authenticated). `reload` re-runs the fetch for the inline
 * error-retry. `baseUrl` is injected (defaulted at the view) so tests can point at
 * an MSW server without touching global config.
 */
export function useDashboard(
  baseUrl: string,
  enabled: boolean,
): {
  state: DashboardState
  reload: () => void
} {
  const client = useMemo(() => createSessionClient(baseUrl), [baseUrl])
  const [state, setState] = useState<DashboardState>({ phase: 'loading' })
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    if (!enabled) return
    let active = true
    setState({ phase: 'loading' })

    void (async () => {
      try {
        const { data } = await client.GET('/me/dashboard')
        if (!active) return
        setState(
          data
            ? { phase: 'loaded', authored: data.authored ?? [], followed: data.followed ?? [] }
            : { phase: 'error' },
        )
      } catch {
        if (active) setState({ phase: 'error' })
      }
    })()

    return () => {
      active = false
    }
  }, [client, enabled, reloadToken])

  const reload = useCallback(() => setReloadToken((token) => token + 1), [])

  return { state, reload }
}
