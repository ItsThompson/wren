import { useProgress } from '../hooks/useProgress'
import { overallCount } from '../progress-derive'
import type { ProgressBinding, RoadmapActions as Actions, Roadmap } from '../types'
import { ProgressBar } from './ProgressBar'
import { RoadmapActions } from './RoadmapActions'
import { SectionBlock } from './SectionBlock'
import { SubjectTags } from './SubjectTags'

interface RoadmapListViewProps {
  roadmap: Roadmap
  /** API base URL, injected so tests can point the progress client at MSW. */
  baseUrl: string
  /** Whether the signed-in user owns this roadmap (owner-only metadata edit). */
  isOwner: boolean
  actions: Actions
}

/**
 * The published-roadmap list view with progress tracking (section 10 "List
 * view"): the header (title, subject tags, overall progress bar), then sections
 * in `section_order`, each with its own bar and interactive checklist. Checking
 * an item persists to the caller's progress record and the bars + subsection
 * done-state update from the derived checked set.
 */
export function RoadmapListView({ roadmap, baseUrl, isOwner, actions }: RoadmapListViewProps) {
  const { checkedIds, toggle } = useProgress(roadmap.id, baseUrl)
  const sectionOrder = roadmap.section_order ?? []
  const sections = roadmap.sections ?? {}
  const suggestedPath = roadmap.suggested_path ?? []
  const overall = overallCount(roadmap, checkedIds)
  const progress: ProgressBinding = { checkedIds, onToggle: toggle }

  return (
    <section className="reading-width py-10">
      <header className="border-b border-border pb-6">
        <h1 className="display-l text-foreground">{roadmap.title}</h1>
        {roadmap.description ? (
          <p className="mt-3 max-w-[52ch] text-muted-foreground">{roadmap.description}</p>
        ) : null}
        <SubjectTags tags={roadmap.subject_tags ?? []} />
        <div className="mt-5">
          <ProgressBar
            checked={overall.checked}
            total={overall.total}
            variant="roadmap"
            label="Overall progress"
          />
        </div>
      </header>

      <RoadmapActions roadmap={roadmap} isOwner={isOwner} actions={actions} />

      <div className="mt-8">
        {sectionOrder.map((id) => {
          const section = sections[id]
          return section ? (
            <SectionBlock
              key={id}
              section={section}
              suggestedPath={suggestedPath}
              progress={progress}
            />
          ) : null
        })}
      </div>
    </section>
  )
}
