import { useCallback, useEffect, useMemo, useState } from 'react'

import { createApiClient } from '@/api/client'
import type { ProfileState } from '../types'

/**
 * Owns the public profile fetch (section 02 US-ACCT-03, `GET /users/{handle}`):
 * a handle's published-public roadmaps. Uses the plain (credential-free) client
 * because the profile is public and viewer-agnostic: no session is sent or
 * needed, and the backend never exposes drafts, private roadmaps, or who follows
 * what.
 *
 * A 404 (unknown handle) resolves to the dedicated `notfound` state rather than a
 * generic error; any other failure is `error` with an inline retry. `reload`
 * re-runs the fetch. `baseUrl` is injected (defaulted at the view) so tests can
 * point at an MSW server without touching global config.
 */
export function useProfile(
  handle: string,
  baseUrl: string,
): {
  state: ProfileState
  reload: () => void
} {
  const client = useMemo(() => createApiClient(baseUrl), [baseUrl])
  const [state, setState] = useState<ProfileState>({ phase: 'loading' })
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    let active = true
    setState({ phase: 'loading' })

    void (async () => {
      try {
        const { data, response } = await client.GET('/users/{handle}', {
          params: { path: { handle } },
        })
        if (!active) return
        if (data) {
          setState({ phase: 'loaded', profile: data })
        } else if (response.status === 404) {
          setState({ phase: 'notfound' })
        } else {
          setState({ phase: 'error' })
        }
      } catch {
        if (active) setState({ phase: 'error' })
      }
    })()

    return () => {
      active = false
    }
  }, [client, handle, reloadToken])

  const reload = useCallback(() => setReloadToken((token) => token + 1), [])

  return { state, reload }
}
