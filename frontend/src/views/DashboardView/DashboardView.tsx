import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { useAuth } from '@/auth'
import { Button } from '@/components/ui/button'
import { DashboardEmpty } from './components/DashboardEmpty'
import { DashboardSection } from './components/DashboardSection'
import { DashboardSkeleton } from './components/DashboardSkeleton'
import { useDashboard } from './hooks/useDashboard'

/**
 * Same-origin by default (dev proxy + MSW); prod points at the API subdomain via
 * `VITE_API_BASE_URL`. Read once at module load: the deployment base is fixed.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

interface DashboardViewProps {
  /** Overridable in tests; defaults to the deployment API base URL. */
  baseUrl?: string
}

/**
 * DashboardView (section 02 US-ACCT-03; section 10 view tree): the caller's
 * private home. It lists everything they authored (draft / private / public) in a
 * "Yours" section and everything they follow in a "Following" section, each card
 * carrying status + visibility badges (section 09 §7.9). Fetching is gated on an
 * authenticated session; the body routes loading / anonymous / error / empty /
 * loaded inside a shared page frame.
 */
export function DashboardView({ baseUrl = API_BASE_URL }: DashboardViewProps) {
  const { status } = useAuth()
  const isAuthenticated = status === 'authenticated'
  const { state, reload } = useDashboard(baseUrl, isAuthenticated)

  let body: ReactNode
  if (status === 'loading') {
    body = <DashboardSkeleton />
  } else if (!isAuthenticated) {
    body = (
      <div className="mt-8 rounded-lg border border-border bg-card p-6">
        <p className="text-muted-foreground">Log in to see your roadmaps and everything you follow.</p>
        <Button asChild className="mt-4">
          <Link to="/auth">Log in</Link>
        </Button>
      </div>
    )
  } else if (state.phase === 'loading') {
    body = <DashboardSkeleton />
  } else if (state.phase === 'error') {
    body = (
      <div className="mt-8 rounded-lg border border-border bg-card p-6">
        <p className="text-muted-foreground">We couldn&rsquo;t load your dashboard.</p>
        <Button variant="outline" className="mt-4" onClick={reload}>
          Try again
        </Button>
      </div>
    )
  } else if (state.authored.length === 0 && state.followed.length === 0) {
    body = <DashboardEmpty />
  } else {
    body = (
      <>
        <DashboardSection
          title="Yours"
          roadmaps={state.authored}
          emptyLabel="You haven't created any roadmaps yet."
        />
        <DashboardSection
          title="Following"
          roadmaps={state.followed}
          emptyLabel="You aren't following any roadmaps yet."
        />
      </>
    )
  }

  return (
    <section className="mx-auto max-w-[1120px] px-5 py-10">
      <header className="border-b border-border pb-6">
        <h1 className="display-l text-foreground">Your dashboard</h1>
        <p className="mt-3 max-w-[52ch] text-muted-foreground">
          Everything you&rsquo;ve created and the roadmaps you&rsquo;re following.
        </p>
      </header>
      {body}
    </section>
  )
}
