import type { PublishState, RoadmapActions as Actions, Roadmap } from '../types'
import { PublishPanel } from './PublishPanel'
import { RoadmapActions } from './RoadmapActions'
import { SectionBlock } from './SectionBlock'
import { SubjectTags } from './SubjectTags'

interface DraftPreviewProps {
  roadmap: Roadmap
  publishState: PublishState
  onPublish: () => void
  /** Whether the signed-in user owns this draft (drafts are owner-only anyway). */
  isOwner: boolean
  actions: Actions
}

/**
 * The owned-draft preview (section 10 "Preview mode"): a header with the title,
 * subject-tag chips, and a clear draft badge, then the sections in
 * `section_order` rendered read-only (no interactive checkboxes: a draft is not
 * startable). The owner publishes from here (section 06 `:publish`); on success
 * the RoadmapView routes to the published list view with progress tracking.
 */
export function DraftPreview({ roadmap, publishState, onPublish, isOwner, actions }: DraftPreviewProps) {
  const sectionOrder = roadmap.section_order ?? []
  const sections = roadmap.sections ?? {}
  const suggestedPath = roadmap.suggested_path ?? []

  return (
    <section className="reading-width py-10">
      <header className="border-b border-border pb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="display-l text-foreground">{roadmap.title}</h1>
          <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Draft · preview
          </span>
        </div>

        {roadmap.description ? (
          <p className="mt-3 max-w-[52ch] text-muted-foreground">{roadmap.description}</p>
        ) : null}

        <SubjectTags tags={roadmap.subject_tags ?? []} />

        <p className="mt-4 text-sm text-muted-foreground">
          This is a preview of your draft. Progress tracking is available once the roadmap is
          published.
        </p>
      </header>

      <RoadmapActions roadmap={roadmap} isOwner={isOwner} actions={actions} />

      <div className="mt-8">
        {sectionOrder.map((id) => {
          const section = sections[id]
          return section ? (
            <SectionBlock key={id} section={section} suggestedPath={suggestedPath} />
          ) : null
        })}
      </div>

      <PublishPanel publishState={publishState} onPublish={onPublish} />
    </section>
  )
}
