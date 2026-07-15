import { Link } from 'react-router'

import type { components } from '@/api'
import { StatusBadge } from './badges/StatusBadge'
import { VisibilityBadge } from './badges/VisibilityBadge'

type RoadmapCardData = components['schemas']['RoadmapCard']

interface RoadmapCardProps {
  roadmap: RoadmapCardData
}

/**
 * A roadmap summarized as a card for the dashboard and profile grids. The whole
 * card is a real link to the roadmap view; it shows
 * the title, the status + visibility badges, and neutral subject-tag chips
 * (subject tags are never hash-colored: only subsection track tags get color).
 */
export function RoadmapCard({ roadmap }: RoadmapCardProps) {
  const subjectTags = roadmap.subject_tags ?? []
  return (
    <Link
      to={`/roadmaps/${roadmap.id}`}
      className="block h-full rounded-lg border border-border bg-card p-5 transition-colors hover:border-input"
    >
      <h3 className="text-lg leading-snug font-semibold text-foreground">{roadmap.title}</h3>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <StatusBadge status={roadmap.status} />
        <VisibilityBadge visibility={roadmap.visibility} />
      </div>
      {subjectTags.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {subjectTags.map((tag) => (
            <li
              key={tag}
              className="rounded-md bg-secondary px-2 py-0.5 text-xs text-secondary-foreground"
            >
              {tag}
            </li>
          ))}
        </ul>
      )}
    </Link>
  )
}
