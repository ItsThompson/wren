import { Link } from 'react-router'

import { EmptyState } from '@/components/states'
import { Button } from '@/components/ui/button'

/**
 * The whole-dashboard empty state: shown when the caller has neither
 * authored nor followed any roadmap. Uses the shared empty-state pattern (a
 * Fraunces line, a muted sub-line, one primary action). Roadmaps are authored by
 * a connected agent, so the action points at the connect-an-agent surface.
 */
export function DashboardEmpty() {
  return (
    <EmptyState
      title="Nothing here yet."
      description="Start your first roadmap by connecting an agent to author one for you."
      action={
        <Button asChild>
          <Link to="/settings/connections">Connect an agent</Link>
        </Button>
      }
    />
  )
}
