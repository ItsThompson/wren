import type { Section } from '../../types'

/**
 * The order subsections render within a section: pedagogical `suggested_path`
 * order first, then any
 * subsection not yet in the path in its structural `subsection_order` position.
 *
 * For a published roadmap `suggested_path` covers every subsection exactly once,
 * so the fallback is empty; for a draft still being authored it keeps
 * not-yet-sequenced subsections visible in a stable order.
 */
export function orderedSubsectionIds(section: Section, suggestedPath: string[]): string[] {
  const structuralOrder = section.subsection_order ?? []
  const membership = new Set(structuralOrder)
  const pathOrder = suggestedPath.filter((id) => membership.has(id))
  const sequenced = new Set(pathOrder)
  const fallback = structuralOrder.filter((id) => !sequenced.has(id))
  return [...pathOrder, ...fallback]
}
