import { orderedSubsectionIds } from '../ordering'
import type { Section } from '../types'
import { NodeCard } from './NodeCard'

interface SectionBlockProps {
  section: Section
  suggestedPath: string[]
}

/**
 * One section header plus its subsections, rendered in `suggested_path` order
 * with a `subsection_order` fallback (section 10 "List view"). No per-section
 * progress bar in preview mode (a draft is not startable).
 */
export function SectionBlock({ section, suggestedPath }: SectionBlockProps) {
  const subsections = section.subsections ?? {}
  const orderedIds = orderedSubsectionIds(section, suggestedPath)

  return (
    <section className="mt-10 first:mt-0">
      <h2 className="display-m mb-4 text-foreground">{section.title}</h2>
      <div className="space-y-4">
        {orderedIds.map((id) => {
          const subsection = subsections[id]
          return subsection ? <NodeCard key={id} subsection={subsection} /> : null
        })}
      </div>
    </section>
  )
}
