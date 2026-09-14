import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { RoadmapFilterActions, RoadmapFilterState } from '../types'
import { FilterChips } from './FilterChips'

interface RoadmapFilterPanelProps {
  state: RoadmapFilterState
  actions: RoadmapFilterActions
}

/** The two-row filter controls for the published roadmap list. */
export function RoadmapFilterPanel({ state, actions }: RoadmapFilterPanelProps) {
  if (state.availableTags.length === 0) return null

  const handleMatchModeChange = (value: string) => {
    if (value === 'any' || value === 'all') actions.setMatchMode(value)
  }

  return (
    <section className="mt-6 border-y border-border py-4" role="group" aria-label="Roadmap filters">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium text-foreground">Match</span>
        <ToggleGroup
          type="single"
          value={state.matchMode}
          onValueChange={handleMatchModeChange}
          aria-label="Match mode"
          variant="outline"
          size="sm"
        >
          <ToggleGroupItem value="any" aria-label="ANY">
            ANY
          </ToggleGroupItem>
          <ToggleGroupItem value="all" aria-label="ALL">
            ALL
          </ToggleGroupItem>
        </ToggleGroup>
        <span className="font-mono text-xs tabular-nums text-muted-foreground" aria-live="polite">
          Showing {state.shownTopicCount} of {state.totalTopicCount} topics
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={actions.clearFilters}
          disabled={state.selectedTags.size === 0}
        >
          Clear filters
        </Button>
      </div>
      <div className="mt-3">
        <FilterChips tags={state.availableTags} selectedTags={state.selectedTags} onToggle={actions.toggleTag} />
      </div>
    </section>
  )
}
