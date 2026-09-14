import { orderedSubsectionIds } from '../util/ordering'
import { sectionCount } from '../util/progress-derive'
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
  /**
   * The canonical matching subsection IDs, or null when nothing is filtered.
   * The section/overall progress bars remain based on the complete roadmap.
   */
  matchingSubsectionIds?: ReadonlySet<string> | null
  /** The current "next" subsection id (from `GET /next`), highlighted in-place. */
  nextSubsectionId?: string | null
}

/**
 * One section header plus its subsections, rendered in `suggested_path` order
 * with a `subsection_order` fallback. When tracking, a
 * per-section progress bar sits under the header; subsections never get a bar.
 * An active filter narrows which subsections show (hiding the whole section
 * when none match); the current-"next" subsection is highlighted.
 */
export function SectionBlock({
  section,
  suggestedPath,
  progress,
  matchingSubsectionIds = null,
  nextSubsectionId = null,
}: SectionBlockProps) {
  const subsections = section.subsections ?? {}
  const orderedIds = orderedSubsectionIds(section, suggestedPath)
  const visibleIds = orderedIds.filter((id) => {
    if (!subsections[id]) return false
    return matchingSubsectionIds === null || matchingSubsectionIds.has(id)
  })
  const count = progress ? sectionCount(section, progress.checkedIds) : null

  // Under an active filter, a section with no matching subsection drops out.
  if (matchingSubsectionIds !== null && visibleIds.length === 0) return null

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
        {visibleIds.map((id) => {
          const subsection = subsections[id]
          return subsection ? (
            <NodeCard
              key={id}
              subsection={subsection}
              progress={progress}
              isNext={id === nextSubsectionId}
            />
          ) : null
        })}
      </div>
    </section>
  )
}
