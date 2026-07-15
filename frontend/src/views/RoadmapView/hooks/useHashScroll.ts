import { useEffect } from 'react'
import { useLocation } from 'react-router'

/**
 * Scroll the element named by the URL hash into view (clicking a
 * tree node navigates to `/roadmaps/{id}#{subsectionId}`, which must land on that
 * subsection in the list view). Runs after the list has rendered and whenever the
 * hash changes; a missing target (e.g. hidden by a filter) is simply a no-op.
 * `enabled` gates it until the roadmap content is on the page.
 */
export function useHashScroll(enabled: boolean): void {
  const { hash } = useLocation()

  useEffect(() => {
    if (!enabled || !hash) return
    const id = decodeURIComponent(hash.slice(1))
    const target = document.getElementById(id)
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [enabled, hash])
}
