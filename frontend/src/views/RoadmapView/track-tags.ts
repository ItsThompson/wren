import type { Roadmap } from './types'

/**
 * The distinct subsection track tags across a roadmap, in first-appearance
 * order (section_order → subsection_order → tag order). These are the tags that
 * become filter chips above the list view (section 10 "List view"). Subject
 * tags are roadmap-level categorization and are never included: only subsection
 * track tags are hash-colored and filterable (section 09 §3.5).
 */
export function collectTrackTags(roadmap: Roadmap): string[] {
  const seen = new Set<string>()
  const tags: string[] = []
  const sections = roadmap.sections ?? {}
  for (const sectionId of roadmap.section_order ?? []) {
    const section = sections[sectionId]
    if (!section) continue
    const subsections = section.subsections ?? {}
    for (const subsectionId of section.subsection_order ?? []) {
      const subsection = subsections[subsectionId]
      if (!subsection) continue
      for (const tag of subsection.tags ?? []) {
        if (seen.has(tag)) continue
        seen.add(tag)
        tags.push(tag)
      }
    }
  }
  return tags
}
