import { Link } from 'react-router'

import { Button } from '@/components/ui/button'

/**
 * The whole-dashboard empty state (section 10): shown when the caller has neither
 * authored nor followed any roadmap. Uses the empty-state pattern (a Fraunces
 * line, a muted sub-line, one primary action). Roadmaps are authored by a
 * connected agent, so the action points at the connect-an-agent surface.
 */
export function DashboardEmpty() {
  return (
    <div className="py-14 text-center">
      <p className="display-m text-foreground">Nothing here yet.</p>
      <p className="mx-auto mt-3 max-w-[44ch] text-muted-foreground">
        Start your first roadmap by connecting an agent to author one for you.
      </p>
      <div className="mt-6 flex justify-center">
        <Button asChild>
          <Link to="/settings/connections">Connect an agent</Link>
        </Button>
      </div>
    </div>
  )
}
