import { useCallback, useState } from 'react'

import { keys, useApiQuery, useSessionClient } from '@/api'
import type { Problem } from '@/lib/problem'

import type { ConsentContextData, ConsentContextState, DecisionState } from '../types'

/** Shown when a decision fails for a reason other than an expired request. */
const GENERIC_ERROR = 'Something went wrong. Please try again.'

/**
 * Derive the consent context phase-state from the SWR read result plus the
 * live-request gate. The gate is false when there is no `auth_request_id` to
 * resolve (no fetch) or a decision reported the parked request gone (404); both
 * collapse to the expired presentation the view renders for `error`. Any read
 * error maps to the generic `error` phase: the hook does not branch on the
 * read's status ("expired" is a view-render concern, matching today).
 */
function toConsentContextState(
  hasLiveRequest: boolean,
  data: ConsentContextData | undefined,
  error: Problem | undefined,
  isLoading: boolean,
): ConsentContextState {
  if (!hasLiveRequest) return { phase: 'error' }
  if (isLoading && !data) return { phase: 'loading' }
  if (error) return { phase: 'error' }
  if (data) return { phase: 'loaded', clientName: data.client_name, scopes: data.scopes }
  return { phase: 'loading' }
}

/**
 * Owns the two consent-flow async concerns: it loads the parked request's
 * context by its opaque `auth_request_id` and submits the human's approve/deny
 * decision. The read goes through {@link useApiQuery} so it binds the shared
 * session client from context: the `.usewren.com` cookie is sent cross-subdomain
 * and the session refreshes transparently. A missing `auth_request_id` passes a
 * `null` key so SWR never fetches, and the view falls straight to the expired
 * state.
 *
 * On a decision the backend mints (approve) or withholds (deny) the code and
 * returns the agent's loopback URL as JSON; the SPA performs the browser
 * navigation itself via `navigateExternal` (a 302 on an XHR would be followed
 * into the loopback and fail CORS). The decision stays imperative. An
 * expired/unknown request (404, on the read or the decision) collapses the whole
 * view into the expired state.
 *
 * `navigateExternal` is injected (defaulted at the view) so tests can assert the
 * navigation without a real redirect.
 */
export function useConsent(
  authRequestId: string,
  navigateExternal: (url: string) => void,
): {
  context: ConsentContextState
  decision: DecisionState
  decide: (approve: boolean) => Promise<void>
} {
  const client = useSessionClient()
  const [decision, setDecision] = useState<DecisionState>({ status: 'idle' })
  const [decisionExpired, setDecisionExpired] = useState(false)

  const { data, error, isLoading } = useApiQuery(
    authRequestId ? keys.consentContext(authRequestId) : null,
    (c) => c.GET('/authorize/context', { params: { query: { auth_request_id: authRequestId } } }),
  )

  const context = toConsentContextState(
    Boolean(authRequestId) && !decisionExpired,
    data,
    error,
    isLoading,
  )

  const decide = useCallback(
    async (approve: boolean) => {
      setDecision({ status: 'submitting' })
      try {
        const { data: decisionData, response } = await client.POST('/authorize/decision', {
          body: { auth_request_id: authRequestId, approve },
        })
        if (decisionData) {
          // Hand the browser to the agent's loopback listener. Stay in the
          // submitting state: the page is navigating away.
          navigateExternal(decisionData.redirect_uri)
          return
        }
        if (response.status === 404) {
          // The parked request is gone: collapse the whole view to expired.
          setDecisionExpired(true)
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
