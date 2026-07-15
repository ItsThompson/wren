import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { useAuth } from '@/auth'
import { EmptyState } from '@/components/states'
import { Button } from '@/components/ui/button'
import { ClientList } from './components/ClientList'
import { ConnectedClientsSkeleton } from './components/ConnectedClientsSkeleton'
import { useConnectedClients } from './hooks/useConnectedClients'

/**
 * ConnectedClientsView (`/me/clients`): the connected-agents
 * management surface. It lists the agents the signed-in user has authorized and
 * lets them revoke access. Fetching is gated on an authenticated session; the
 * body routes loading / anonymous / error / empty / loaded states inside a
 * shared page frame.
 */
export function ConnectedClientsView() {
  const { status } = useAuth()
  const isAuthenticated = status === 'authenticated'
  const { state, revoke, reload } = useConnectedClients(isAuthenticated)

  let body: ReactNode
  if (status === 'loading') {
    body = <ConnectedClientsSkeleton />
  } else if (!isAuthenticated) {
    body = (
      <div className="rounded-lg border border-border bg-card p-6">
        <p className="text-muted-foreground">
          Log in to view and manage the agents connected to your account.
        </p>
        <Button asChild className="mt-4">
          <Link to="/auth">Log in</Link>
        </Button>
      </div>
    )
  } else if (state.phase === 'loading') {
    body = <ConnectedClientsSkeleton />
  } else if (state.phase === 'error') {
    body = (
      <div className="rounded-lg border border-border bg-card p-6">
        <p className="text-muted-foreground">We couldn&rsquo;t load your connected agents.</p>
        <Button variant="outline" className="mt-4" onClick={reload}>
          Try again
        </Button>
      </div>
    )
  } else if (state.clients.length === 0) {
    body = (
      <EmptyState
        title="No connected agents yet."
        description="When you authorize an agent from your MCP client, it will appear here."
      />
    )
  } else {
    body = <ClientList clients={state.clients} onRevoke={revoke} />
  }

  return (
    <section className="reading-width py-10">
      <header className="border-b border-border pb-6">
        <h1 className="display-l text-foreground">Connected agents</h1>
        <p className="mt-3 max-w-[52ch] text-muted-foreground">
          Agents you have authorized to act on your behalf. Revoke access at any time.
        </p>
      </header>
      <div className="mt-8">{body}</div>
    </section>
  )
}
