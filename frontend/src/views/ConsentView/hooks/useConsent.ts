import { useCallback, useEffect, useMemo, useState } from 'react'

import { createSessionClient } from '@/auth/createSessionClient'
import type { ConsentContextState, DecisionState } from '../types'

/** Shown when a decision fails for a reason other than an expired request. */
const GENERIC_ERROR = 'Something went wrong. Please try again.'

/**
 * Owns the two consent-flow async concerns (section 08): it loads the parked
 * request's context by its opaque `auth_request_id` and submits the human's
 * approve/deny decision. The session-aware client sends the `.usewren.com`
 * cookie cross-subdomain (CORS + credentials) and refreshes transparently.
 *
 * On a decision the backend mints (approve) or withholds (deny) the code and
 * returns the agent's loopback URL as JSON; the SPA performs the browser
 * navigation itself via `navigateExternal` (a 302 on an XHR would be followed
 * into the loopback and fail CORS). An expired/unknown request (404) collapses
 * the whole view into the expired state.
 *
 * `baseUrl` and `navigateExternal` are injected (defaulted at the view) so tests
 * can point at an MSW server and assert the navigation without a real redirect.
 */
export function useConsent(
  authRequestId: string,
  baseUrl: string,
  navigateExternal: (url: string) => void,
): {
  context: ConsentContextState
  decision: DecisionState
  decide: (approve: boolean) => Promise<void>
} {
  const client = useMemo(() => createSessionClient(baseUrl), [baseUrl])
  const [context, setContext] = useState<ConsentContextState>({ phase: 'loading' })
  const [decision, setDecision] = useState<DecisionState>({ status: 'idle' })

  useEffect(() => {
    if (!authRequestId) {
      // No parked request to resolve: nothing to consent to.
      setContext({ phase: 'error' })
      return
    }
    let active = true
    setContext({ phase: 'loading' })

    void (async () => {
      try {
        const { data } = await client.GET('/authorize/context', {
          params: { query: { auth_request_id: authRequestId } },
        })
        if (!active) return
        setContext(
          data
            ? { phase: 'loaded', clientName: data.client_name, scopes: data.scopes }
            : { phase: 'error' },
        )
      } catch {
        // Network failure / unreachable backend: surface the expired-style error
        // rather than hang on the spinner.
        if (active) setContext({ phase: 'error' })
      }
    })()

    return () => {
      active = false
    }
  }, [client, authRequestId])

  const decide = useCallback(
    async (approve: boolean) => {
      setDecision({ status: 'submitting' })
      try {
        const { data, response } = await client.POST('/authorize/decision', {
          body: { auth_request_id: authRequestId, approve },
        })
        if (data) {
          // Hand the browser to the agent's loopback listener. Stay in the
          // submitting state: the page is navigating away.
          navigateExternal(data.redirect_uri)
          return
        }
        if (response.status === 404) {
          setContext({ phase: 'error' })
          return
        }
        setDecision({ status: 'error', message: GENERIC_ERROR })
      } catch {
        setDecision({ status: 'error', message: GENERIC_ERROR })
      }
    },
    [client, authRequestId, navigateExternal],
  )

  return { context, decision, decide }
}
