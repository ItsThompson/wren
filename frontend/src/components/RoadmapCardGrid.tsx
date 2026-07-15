import type { components } from '@/api'
import { RoadmapCard } from './RoadmapCard'

type RoadmapCardData = components['schemas']['RoadmapCard']

interface RoadmapCardGridProps {
  roadmaps: RoadmapCardData[]
}

/**
 * A responsive grid of {@link RoadmapCard}s, shared by the dashboard sections and
 * the profile view (spec section 09: wider grid layout for these list views).
 */
export function RoadmapCardGrid({ roadmaps }: RoadmapCardGridProps) {
  return (
    <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {roadmaps.map((roadmap) => (
        <li key={roadmap.id}>
          <RoadmapCard roadmap={roadmap} />
        </li>
      ))}
    </ul>
  )
}
