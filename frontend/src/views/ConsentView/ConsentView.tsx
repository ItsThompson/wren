import { useSearchParams } from 'react-router'

import { useAuth } from '@/auth'
import { ConsentCard } from './components/ConsentCard'
import { ConsentError } from './components/ConsentError'
import { ConsentLogin } from './components/ConsentLogin'
import { ConsentSpinner } from './components/ConsentSpinner'
import { useConsent } from './hooks/useConsent'

/** Hand the browser to an external URL (the agent's loopback listener). */
function assignLocation(url: string): void {
  window.location.assign(url)
}

interface ConsentViewProps {
  /** Overridable in tests; defaults to a real browser navigation. */
  navigateExternal?: (url: string) => void
}

/**
 * ConsentView: the OAuth consent screen. It reads the opaque
 * `auth_request_id` from the query, loads the parked request's context, prompts
 * login when there is no session, and posts the approve/deny decision, then
 * navigates the browser to the returned agent loopback URL.
 *
 * The four states route in priority order: an expired/unknown request shows the
 * expired message; a pending context (or an unresolved session) shows the
 * spinner; an anonymous visitor gets the login gate; an authenticated visitor
 * gets the decision card.
 */
export function ConsentView({ navigateExternal = assignLocation }: ConsentViewProps) {
  const [searchParams] = useSearchParams()
  const authRequestId = searchParams.get('auth_request_id') ?? ''
  const { status, user } = useAuth()
  const { context, decision, decide } = useConsent(authRequestId, navigateExternal)

  if (context.phase === 'error') {
    return <ConsentError />
  }
  if (context.phase === 'loading' || status === 'loading') {
    return <ConsentSpinner />
  }
  if (status !== 'authenticated') {
    return <ConsentLogin clientName={context.clientName} />
  }

  return (
    <ConsentCard
      clientName={context.clientName}
      userName={user?.username ?? 'you'}
      scopes={context.scopes}
      pending={decision.status === 'submitting'}
      error={decision.status === 'error' ? decision.message : null}
      onApprove={() => {
        void decide(true)
      }}
      onDeny={() => {
        void decide(false)
      }}
    />
  )
}
