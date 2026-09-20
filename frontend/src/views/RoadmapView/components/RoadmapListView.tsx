import { InlineNotice, StaleRevisionNotice } from '@/components/states'
import { RoadmapViewTabs } from '@/components/RoadmapViewTabs'
import { useHashScroll } from '../hooks/useHashScroll'
import { useProgress } from '../hooks/useProgress'
import { useRoadmapFilters } from '../hooks/useRoadmapFilters'
import { overallCount } from '../util/progress-derive'
import type { ProgressBinding, RoadmapActions as Actions, Roadmap } from '../types'
import { DeadlineCountdown } from './DeadlineCountdown'
import { FilterEmptyState } from './FilterEmptyState'
import { NextComplete } from './NextComplete'
import { ProgressBar } from './ProgressBar'
import { RoadmapActions } from './RoadmapActions'
import { SectionBlock } from './SectionBlock'
import { SubjectTags } from './SubjectTags'
import { ReadOnlyNotice } from './ReadOnlyNotice'
import { RoadmapFilterPanel } from './RoadmapFilterPanel'

interface RoadmapListViewProps {
  roadmap: Roadmap
  /** Whether the signed-in user owns this roadmap (owner-only metadata edit). */
  isOwner: boolean
  /** Whether personal progress and actions are available. */
  isAuthenticated: boolean
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
export function RoadmapListView({ roadmap, isOwner, isAuthenticated, actions, onReload }: RoadmapListViewProps) {
  const {
    checkedIds,
    progressState,
    toggle,
    deadline,
    setDeadline,
    nextSubsectionId,
    nextComplete,
    notice,
    dismissNotice,
    reload,
  } = useProgress(roadmap.id, roadmap.status)
  const sectionOrder = roadmap.section_order ?? []
  const sections = roadmap.sections ?? {}
  const suggestedPath = roadmap.suggested_path ?? []
  const { state: filterState, actions: filterActions } = useRoadmapFilters(roadmap)
  const overall = progressState.phase === 'ready' && checkedIds ? overallCount(roadmap, checkedIds) : null
  const progress: ProgressBinding | undefined =
    progressState.phase === 'ready' && checkedIds ? { checkedIds, onToggle: toggle } : undefined

  useHashScroll(true)

  // A stale-write re-read reloads both the roadmap document and the progress.
  const handleStaleReload = () => {
    reload()
    onReload()
  }
  const handleProgressReload = () => {
    reload()
  }

  return (
    <section className="reading-width py-10">
      <header className="border-b border-border pb-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <h1 className="display-l min-w-0 max-w-full break-words text-foreground">{roadmap.title}</h1>
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
            {isAuthenticated
              ? 'This roadmap is archived: hidden from discovery, but you keep it and your progress.'
              : 'This roadmap is archived: hidden from discovery, but available here for reading.'}
          </p>
        ) : null}
        {roadmap.description ? <p className="mt-3 w-full text-muted-foreground">{roadmap.description}</p> : null}
        <SubjectTags tags={roadmap.subject_tags ?? []} />
        <div className="mt-5">
          {overall ? (
            <ProgressBar checked={overall.checked} total={overall.total} variant="roadmap" label="Overall progress" />
          ) : null}
          {isAuthenticated && progressState.phase === 'loading' ? (
            <p className="text-sm text-muted-foreground" role="status">
              Loading progress…
            </p>
          ) : null}
          {isAuthenticated && progressState.phase === 'closed' ? (
            <p className="text-sm text-muted-foreground" role="status">
              This archived roadmap is closed to new tracking. Existing followers keep their progress.
            </p>
          ) : null}
          {isAuthenticated && progressState.phase === 'failed' ? (
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground" role="alert">
              <span>We couldn’t load your progress.</span>
              <button
                type="button"
                className="text-primary underline-offset-4 hover:underline"
                onClick={handleProgressReload}
              >
                Try again
              </button>
            </div>
          ) : null}
        </div>
        {isAuthenticated && progressState.phase === 'ready' ? (
          <DeadlineCountdown deadline={deadline} onSet={setDeadline} />
        ) : null}
      </header>

      {isAuthenticated ? <RoadmapActions roadmap={roadmap} isOwner={isOwner} actions={actions} /> : <ReadOnlyNotice />}

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

      {isAuthenticated && progressState.phase === 'ready' && nextComplete ? <NextComplete /> : null}

      <RoadmapFilterPanel state={filterState} actions={filterActions} />

      {filterState.selectedTags.size > 0 && filterState.shownTopicCount === 0 ? (
        <FilterEmptyState onClear={filterActions.clearFilters} />
      ) : (
        <div className="mt-8">
          {sectionOrder.map((id) => {
            const section = sections[id]
            return section ? (
              <SectionBlock
                key={id}
                section={section}
                suggestedPath={suggestedPath}
                progress={progress}
                matchingSubsectionIds={filterState.matchingSubsectionIds}
                nextSubsectionId={nextSubsectionId}
              />
            ) : null
          })}
        </div>
      )}
    </section>
  )
}
