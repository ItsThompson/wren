import { Link } from 'react-router'

interface RoadmapViewTabsProps {
  roadmapId: string
  /** Which view is showing; the other becomes a link. */
  active: 'list' | 'tree'
}

const TAB_BASE = 'rounded-md px-3 py-1 text-sm font-medium transition-colors'
const ACTIVE_TAB = 'bg-accent text-accent-foreground'
const INACTIVE_TAB = 'text-muted-foreground no-underline hover:text-foreground'

/**
 * The List/Tree view switcher shared by both roadmap views. The active view
 * renders as a static segment (`aria-current="page"`) and the other as a real
 * `<Link>`, giving both
 * directions (List->Tree and Tree->List) one consistent entry point.
 */
export function RoadmapViewTabs({ roadmapId, active }: RoadmapViewTabsProps) {
  return (
    <nav
      aria-label="Roadmap views"
      className="flex items-center gap-1 rounded-lg border border-border bg-card p-1"
    >
      {active === 'list' ? (
        <span aria-current="page" className={`${TAB_BASE} ${ACTIVE_TAB}`}>
          List
        </span>
      ) : (
        <Link to={`/roadmaps/${roadmapId}`} className={`${TAB_BASE} ${INACTIVE_TAB}`}>
          List
        </Link>
      )}
      {active === 'tree' ? (
        <span aria-current="page" className={`${TAB_BASE} ${ACTIVE_TAB}`}>
          Tree
        </span>
      ) : (
        <Link to={`/roadmaps/${roadmapId}/tree`} className={`${TAB_BASE} ${INACTIVE_TAB}`}>
          Tree
        </Link>
      )}
    </nav>
  )
}
