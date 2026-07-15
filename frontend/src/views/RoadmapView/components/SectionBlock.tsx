import { orderedSubsectionIds } from '../ordering'
import { sectionCount } from '../progress-derive'
import type { ProgressBinding, Section } from '../types'
import { NodeCard } from './NodeCard'
import { ProgressBar } from './ProgressBar'

interface SectionBlockProps {
  section: Section
  suggestedPath: string[]
  /**
   * Present on a published roadmap being tracked: renders the per-section
   * progress bar and threads the binding to each NodeCard. Absent in draft
   * preview mode (a draft is not startable, so no bar and no checkboxes).
   */
  progress?: ProgressBinding
}

/**
 * One section header plus its subsections, rendered in `suggested_path` order
 * with a `subsection_order` fallback (section 10 "List view"). When tracking, a
 * per-section progress bar sits under the header; subsections never get a bar.
 */
export function SectionBlock({ section, suggestedPath, progress }: SectionBlockProps) {
  const subsections = section.subsections ?? {}
  const orderedIds = orderedSubsectionIds(section, suggestedPath)
  const count = progress ? sectionCount(section, progress.checkedIds) : null

  return (
    <section className="mt-10 first:mt-0">
      <h2 className="display-m mb-3 text-foreground">{section.title}</h2>
      {count ? (
        <div className="mb-4">
          <ProgressBar
            checked={count.checked}
            total={count.total}
            variant="section"
            label={`${section.title} progress`}
          />
        </div>
      ) : null}
      <div className="space-y-4">
        {orderedIds.map((id) => {
          const subsection = subsections[id]
          return subsection ? (
            <NodeCard key={id} subsection={subsection} progress={progress} />
          ) : null
        })}
      </div>
    </section>
  )
}
