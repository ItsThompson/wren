import type { FilterMatchMode, Roadmap, Subsection } from '../../types'

export interface TrackTagMatchResult {
  availableTags: string[]
  matchingSubsectionIds: ReadonlySet<string> | null
  shownTopicCount: number
  totalTopicCount: number
}

interface OrderedSubsection {
  id: string
  subsection: Subsection
}

function orderedSubsections(roadmap: Roadmap): OrderedSubsection[] {
  const ordered: OrderedSubsection[] = []
  const sections = roadmap.sections ?? {}

  for (const sectionId of roadmap.section_order ?? []) {
    const section = sections[sectionId]
    if (!section) continue
    const subsections = section.subsections ?? {}
    for (const subsectionId of section.subsection_order ?? []) {
      const subsection = subsections[subsectionId]
      if (!subsection) continue
      ordered.push({ id: subsectionId, subsection })
    }
  }

  return ordered
}

/** The distinct subsection track tags in structural first-appearance order. */
export function collectTrackTags(roadmap: Roadmap): string[] {
  const seen = new Set<string>()
  const tags: string[] = []

  for (const { subsection } of orderedSubsections(roadmap)) {
    for (const tag of subsection.tags ?? []) {
      if (seen.has(tag)) continue
      seen.add(tag)
      tags.push(tag)
    }
  }

  return tags
}

/** Derive the complete presentation result for one roadmap filter selection. */
export function deriveTrackTagMatches(
  roadmap: Roadmap,
  selectedTags: ReadonlySet<string>,
  matchMode: FilterMatchMode,
): TrackTagMatchResult {
  const ordered = orderedSubsections(roadmap)
  const availableTags = collectTrackTags(roadmap)
  const totalTopicCount = ordered.length

  if (selectedTags.size === 0) {
    return {
      availableTags,
      matchingSubsectionIds: null,
      shownTopicCount: totalTopicCount,
      totalTopicCount,
    }
  }

  const matchingSubsectionIds = new Set<string>()
  for (const { id, subsection } of ordered) {
    const topicTags = new Set(subsection.tags ?? [])
    const matches =
      matchMode === 'any'
        ? [...selectedTags].some((tag) => topicTags.has(tag))
        : [...selectedTags].every((tag) => topicTags.has(tag))
    if (matches) matchingSubsectionIds.add(id)
  }

  return {
    availableTags,
    matchingSubsectionIds,
    shownTopicCount: matchingSubsectionIds.size,
    totalTopicCount,
  }
}
