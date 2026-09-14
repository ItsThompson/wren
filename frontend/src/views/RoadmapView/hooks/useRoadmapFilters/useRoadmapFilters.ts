import { useCallback, useEffect, useMemo, useState } from 'react'

import { deriveTrackTagMatches } from '../../util/track-tags'
import type {
  FilterMatchMode,
  Roadmap,
  RoadmapFilterActions,
  RoadmapFilterState,
} from '../../types'

interface RoadmapFiltersResult {
  state: RoadmapFilterState
  actions: RoadmapFilterActions
}

export function useRoadmapFilters(roadmap: Roadmap): RoadmapFiltersResult {
  const [selectedTags, setSelectedTags] = useState<ReadonlySet<string>>(() => new Set())
  const [matchMode, setMatchMode] = useState<FilterMatchMode>('any')

  const unfiltered = useMemo(
    () => deriveTrackTagMatches(roadmap, new Set(), 'any'),
    [roadmap],
  )
  const validSelectedTags = useMemo(() => {
    const available = new Set(unfiltered.availableTags)
    return new Set([...selectedTags].filter((tag) => available.has(tag)))
  }, [selectedTags, unfiltered.availableTags])

  useEffect(() => {
    if (validSelectedTags.size === selectedTags.size) return
    setSelectedTags(validSelectedTags)
  }, [selectedTags.size, validSelectedTags])

  const derived = useMemo(
    () => deriveTrackTagMatches(roadmap, validSelectedTags, matchMode),
    [matchMode, roadmap, validSelectedTags],
  )

  const toggleTag = useCallback(
    (tag: string) => {
      if (!unfiltered.availableTags.includes(tag)) return
      setSelectedTags((current) => {
        const next = new Set(current)
        if (next.has(tag)) next.delete(tag)
        else next.add(tag)
        return next
      })
    },
    [unfiltered.availableTags],
  )

  const clearFilters = useCallback(() => setSelectedTags(new Set()), [])

  return {
    state: {
      availableTags: derived.availableTags,
      selectedTags: validSelectedTags,
      matchMode,
      matchingSubsectionIds: derived.matchingSubsectionIds,
      shownTopicCount: derived.shownTopicCount,
      totalTopicCount: derived.totalTopicCount,
    },
    actions: {
      toggleTag,
      setMatchMode,
      clearFilters,
    },
  }
}
