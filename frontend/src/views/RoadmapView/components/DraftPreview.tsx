import type { Roadmap } from '../types'
import { SectionBlock } from './SectionBlock'

interface DraftPreviewProps {
  roadmap: Roadmap
}

/**
 * The owned-draft list preview (section 10 "Preview mode"): a header with the
 * title, subject-tag chips, and a clear draft badge, then the sections in
 * `section_order`. Preview is read-only: no follow action and no persisting
 * checkboxes, because a draft is not startable.
 */
export function DraftPreview({ roadmap }: DraftPreviewProps) {
  const sectionOrder = roadmap.section_order ?? []
  const sections = roadmap.sections ?? {}
  const subjectTags = roadmap.subject_tags ?? []
  const suggestedPath = roadmap.suggested_path ?? []
  const isDraft = roadmap.status === 'draft'

  return (
    <section className="reading-width py-10">
      <header className="border-b border-border pb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="display-l text-foreground">{roadmap.title}</h1>
          {isDraft ? (
            <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Draft · preview
            </span>
          ) : null}
        </div>

        {roadmap.description ? (
          <p className="mt-3 max-w-[52ch] text-muted-foreground">{roadmap.description}</p>
        ) : null}

        {subjectTags.length > 0 ? (
          <ul className="mt-4 flex flex-wrap gap-2">
            {subjectTags.map((tag) => (
              <li
                key={tag}
                className="rounded-md bg-secondary px-2 py-0.5 text-xs text-secondary-foreground"
              >
                {tag}
              </li>
            ))}
          </ul>
        ) : null}

        {isDraft ? (
          <p className="mt-4 text-sm text-muted-foreground">
            This is a preview of your draft. Progress tracking is available once the roadmap is
            published.
          </p>
        ) : null}
      </header>

      <div className="mt-8">
        {sectionOrder.map((id) => {
          const section = sections[id]
          return section ? (
            <SectionBlock key={id} section={section} suggestedPath={suggestedPath} />
          ) : null
        })}
      </div>
    </section>
  )
}
