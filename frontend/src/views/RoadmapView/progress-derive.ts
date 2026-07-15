import type { Roadmap, Section, Subsection } from './types'

/**
 * Pure client-side progress derivation: overall and
 * per-section completion counts and per-subsection done-state, computed from the
 * roadmap plus the set of checked item ids. Done-state is **derived**, never
 * stored, so the bars and check styling update instantly from
 * the local checked set while the write reconciles in the background.
 *
 * The backend computes the authoritative snapshot too (`progress.summary`); this
 * mirror exists so the SPA can reflect a toggle without waiting for a round trip.
 */

export interface DerivedCount {
  total: number
  checked: number
  percent: number
}

function percent(checked: number, total: number): number {
  return total === 0 ? 0 : Math.round((checked / total) * 100)
}

/** True when a subsection has items and every one of them is checked. */
export function isSubsectionDone(subsection: Subsection, checkedIds: Set<string>): boolean {
  const itemIds = subsection.item_order ?? []
  return itemIds.length > 0 && itemIds.every((id) => checkedIds.has(id))
}

/** Completion count across one section's subsections. */
export function sectionCount(section: Section, checkedIds: Set<string>): DerivedCount {
  let total = 0
  let checked = 0
  const subsections = section.subsections ?? {}
  for (const subId of section.subsection_order ?? []) {
    const subsection = subsections[subId]
    if (!subsection) continue
    for (const itemId of subsection.item_order ?? []) {
      total += 1
      if (checkedIds.has(itemId)) checked += 1
    }
  }
  return { total, checked, percent: percent(checked, total) }
}

/** Completion count across the whole roadmap. */
export function overallCount(roadmap: Roadmap, checkedIds: Set<string>): DerivedCount {
  let total = 0
  let checked = 0
  const sections = roadmap.sections ?? {}
  for (const sectionId of roadmap.section_order ?? []) {
    const section = sections[sectionId]
    if (!section) continue
    const count = sectionCount(section, checkedIds)
    total += count.total
    checked += count.checked
  }
  return { total, checked, percent: percent(checked, total) }
}
