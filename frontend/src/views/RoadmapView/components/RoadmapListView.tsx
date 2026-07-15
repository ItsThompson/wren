import { useMemo, useState } from 'react'

import { InlineNotice, StaleRevisionNotice } from '@/components/states'
import { RoadmapViewTabs } from '@/components/RoadmapViewTabs'
import { useHashScroll } from '../hooks/useHashScroll'
import { useProgress } from '../hooks/useProgress'
import { overallCount } from '../progress-derive'
import { collectTrackTags } from '../track-tags'
import type { ProgressBinding, RoadmapActions as Actions, Roadmap } from '../types'
import { DeadlineCountdown } from './DeadlineCountdown'
import { FilterChips } from './FilterChips'
import { NextComplete } from './NextComplete'
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
  /** Refetch the roadmap itself; paired with a progress reload for a re-read. */
  onReload: () => void
}

/**
 * The published-roadmap list view with progress tracking: the header (title,
 * subject tags, overall progress bar, deadline
 * countdown, List/Tree tabs), track-tag filter chips, then sections in
 * `section_order`, each with its own bar and interactive checklist. Checking an
 * item persists to the caller's progress record and the bars + subsection
 * done-state update from the derived checked set; a failed persist is reverted
 * and surfaced (a 409 as the ochre re-read prompt, otherwise a quiet notice).
 * When the suggested path is complete, a calm completion state replaces the
 * "next" highlight. A `#{subsectionId}` hash (e.g. from the tree view) scrolls to
 * that node.
 */
export function RoadmapListView({ roadmap, baseUrl, isOwner, actions, onReload }: RoadmapListViewProps) {
  const { checkedIds, toggle, deadline, setDeadline, nextSubsectionId, nextComplete, notice, dismissNotice, reload } =
    useProgress(roadmap.id, baseUrl)
  const [activeTag, setActiveTag] = useState<string | null>(null)
  const sectionOrder = roadmap.section_order ?? []
  const sections = roadmap.sections ?? {}
  const suggestedPath = roadmap.suggested_path ?? []
  const trackTags = useMemo(() => collectTrackTags(roadmap), [roadmap])
  const overall = overallCount(roadmap, checkedIds)
  const progress: ProgressBinding = { checkedIds, onToggle: toggle }

  useHashScroll(true)

  // Selecting the active tag again clears the filter and restores all sections.
  const toggleTag = (tag: string) => setActiveTag((current) => (current === tag ? null : tag))

  // A stale-write re-read reloads both the roadmap document and the progress.
  const handleStaleReload = () => {
    reload()
    onReload()
  }

  return (
    <section className="reading-width py-10">
      <header className="border-b border-border pb-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="display-l text-foreground">{roadmap.title}</h1>
            {roadmap.status === 'archived' ? (
              <span className="rounded-full border border-muted-foreground/50 px-3 py-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Archived
              </span>
            ) : null}
          </div>
          <RoadmapViewTabs roadmapId={roadmap.id} active="list" />
        </div>
        {roadmap.status === 'archived' ? (
          <p className="mt-2 text-sm text-muted-foreground">
            This roadmap is archived: hidden from discovery, but you keep it and your progress.
          </p>
        ) : null}
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
        <DeadlineCountdown deadline={deadline} onSet={setDeadline} />
      </header>

      <RoadmapActions roadmap={roadmap} isOwner={isOwner} actions={actions} />

      {notice?.kind === 'stale' ? (
        <div className="mt-6">
          <StaleRevisionNotice onReload={handleStaleReload} />
        </div>
      ) : null}
      {notice?.kind === 'save-failed' ? (
        <div className="mt-6">
          <InlineNotice onDismiss={dismissNotice}>
            We couldn’t save that change, so we undid it. Check your connection and try again.
          </InlineNotice>
        </div>
      ) : null}

      {nextComplete ? <NextComplete /> : null}

      <FilterChips tags={trackTags} activeTag={activeTag} onToggle={toggleTag} />

      <div className="mt-8">
        {sectionOrder.map((id) => {
          const section = sections[id]
          return section ? (
            <SectionBlock
              key={id}
              section={section}
              suggestedPath={suggestedPath}
              progress={progress}
              activeTag={activeTag}
              nextSubsectionId={nextSubsectionId}
            />
          ) : null
        })}
      </div>
    </section>
  )
}
