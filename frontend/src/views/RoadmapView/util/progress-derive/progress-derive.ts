import type { NextResult, ProgressSnapshot, Roadmap, Section, Subsection } from '../../types'

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

/** The current "next" subsection id from a `GET /next` response, or null when
 * the path is done / no suggestion is available. Extracted so the mount read and
 * the toggle reconcile derive it the same way. */
export function firstNextSubsectionId(next: NextResult | undefined): string | null {
  return next?.items?.[0]?.subsection_id ?? null
}

/**
 * A minimal conforming {@link ProgressSnapshot} for a roadmap whose progress read
 * has not resolved (the read is best-effort). The counts are placeholders (the
 * list view derives its bars from the roadmap + checked set, not these fields);
 * this only exists so an optimistic updater never writes a partial, non-conforming
 * cache entry when no snapshot has loaded yet.
 */
function emptyProgressSnapshot(roadmapId: string): ProgressSnapshot {
  return { roadmap_id: roadmapId, total_items: 0, checked_items: 0, percent: 0, checked_ids: [] }
}

/**
 * Apply an optimistic check/uncheck to a cached progress snapshot's `checked_ids`.
 * A functional updater for `mutate(keys.progress(id))` so it composes with an
 * interleaved deadline write instead of overwriting the whole snapshot. Seeds a
 * minimal snapshot from `roadmapId` when none has loaded, so the optimistic
 * checkbox still reflects even when the best-effort progress read failed.
 */
export function patchCheckedIds(
  snapshot: ProgressSnapshot | undefined,
  roadmapId: string,
  itemId: string,
  checked: boolean,
): ProgressSnapshot {
  const base = snapshot ?? emptyProgressSnapshot(roadmapId)
  const nextChecked = new Set(base.checked_ids ?? [])
  if (checked) nextChecked.add(itemId)
  else nextChecked.delete(itemId)
  return { ...base, checked_ids: [...nextChecked] }
}

/**
 * Fold a deadline into a cached progress snapshot. A functional updater for
 * `mutate(keys.progress(id))` so it composes with an interleaved check write
 * rather than clobbering `checked_ids`, and guards an unresolved snapshot the
 * same way {@link patchCheckedIds} does so it never writes a non-conforming entry.
 */
export function patchDeadline(
  snapshot: ProgressSnapshot | undefined,
  roadmapId: string,
  deadline: string | null,
): ProgressSnapshot {
  const base = snapshot ?? emptyProgressSnapshot(roadmapId)
  return { ...base, deadline }
}
