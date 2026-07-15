import { RoadmapCardGrid } from '@/components/RoadmapCardGrid'
import type { RoadmapCardData } from '../types'

interface DashboardSectionProps {
  title: string
  roadmaps: RoadmapCardData[]
  emptyLabel: string
}

/**
 * One titled dashboard section ("Yours" or "Following", section 09 §7.9). Renders
 * the roadmap-card grid, or a quiet muted line when this particular list is empty
 * (the whole-dashboard empty state is handled a level up).
 */
export function DashboardSection({ title, roadmaps, emptyLabel }: DashboardSectionProps) {
  return (
    <section className="mt-8">
      <h2 className="text-xl font-semibold text-foreground">{title}</h2>
      {roadmaps.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">{emptyLabel}</p>
      ) : (
        <div className="mt-4">
          <RoadmapCardGrid roadmaps={roadmaps} />
        </div>
      )}
    </section>
  )
}
