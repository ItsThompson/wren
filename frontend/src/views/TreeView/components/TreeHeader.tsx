import { RoadmapViewTabs } from '@/components/RoadmapViewTabs'

interface TreeHeaderProps {
  roadmapId: string
  title: string
}

/**
 * The tree-view header. Shows the roadmap title plus the shared List/Tree
 * switcher with Tree
 * active, so List links back to the primary reading view at `/roadmaps/{id}`.
 */
export function TreeHeader({ roadmapId, title }: TreeHeaderProps) {
  return (
    <header className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4">
      <h1 className="display-m text-foreground">{title}</h1>
      <RoadmapViewTabs roadmapId={roadmapId} active="tree" />
    </header>
  )
}
