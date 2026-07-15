import { Link } from 'react-router'

interface TreeHeaderProps {
  roadmapId: string
  title: string
}

/**
 * The tree-view header (spec section 10 "RoadmapView owns ... tab: list |
 * tree"). Shows the roadmap title plus a List/Tree toggle; Tree is the active
 * tab here and List links back to the primary reading view at `/roadmaps/{id}`.
 */
export function TreeHeader({ roadmapId, title }: TreeHeaderProps) {
  return (
    <header className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4">
      <h1 className="display-m text-foreground">{title}</h1>
      <nav
        aria-label="Roadmap views"
        className="flex items-center gap-1 rounded-lg border border-border bg-card p-1"
      >
        <Link
          to={`/roadmaps/${roadmapId}`}
          className="rounded-md px-3 py-1 text-sm font-medium text-muted-foreground no-underline transition-colors hover:text-foreground"
        >
          List
        </Link>
        <span
          aria-current="page"
          className="rounded-md bg-accent px-3 py-1 text-sm font-medium text-accent-foreground"
        >
          Tree
        </span>
      </nav>
    </header>
  )
}
