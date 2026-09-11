import { describe, expect, it } from 'vitest'

import type { Dashboard, Profile, Roadmap } from './cache-reconciliation'
import {
  addAuthoredRoadmap,
  reconcileDashboard,
  reconcileProfile,
  removeRoadmapFromDashboard,
  removeRoadmapFromProfile,
} from './cache-reconciliation'

function roadmap(overrides: Partial<Roadmap> = {}): Roadmap {
  return {
    id: 'r1',
    owner: 'u1',
    title: 'Roadmap',
    visibility: 'public',
    status: 'published',
    revision: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

const card = { id: 'r1', title: 'Old', status: 'published' as const, visibility: 'public' as const }
const dashboard: Dashboard = { authored: [card], followed: [card] }
const profile: Profile = { handle: 'ada', display_name: 'Ada', roadmaps: [card] }

describe('roadmap cache reconciliation', () => {
  it('updates authored and followed projections from a returned roadmap', () => {
    const updated = roadmap({ title: 'New title', subject_tags: ['algorithms'] })
    expect(reconcileDashboard(dashboard, updated)).toEqual({
      authored: [{ ...card, title: 'New title', subject_tags: ['algorithms'] }],
      followed: [{ ...card, title: 'New title', subject_tags: ['algorithms'] }],
    })
  })

  it('removes private or archived cards from the appropriate discovery projection', () => {
    const archived = roadmap({ status: 'archived' })
    expect(reconcileProfile(profile, archived)?.roadmaps).toEqual([])
    expect(reconcileDashboard(dashboard, roadmap({ visibility: 'private' }))?.followed).toEqual([])
  })

  it('adds a newly forked roadmap once to authored dashboard data', () => {
    const fork = roadmap({ id: 'r2', status: 'draft', visibility: 'private' })
    const added = addAuthoredRoadmap({ authored: [], followed: [] }, fork)
    expect(added?.authored).toEqual([{ id: 'r2', title: 'Roadmap', status: 'draft', visibility: 'private' }])
    expect(addAuthoredRoadmap(added, fork)).toBe(added)
  })

  it('removes deleted cards from dashboard and profile caches', () => {
    expect(removeRoadmapFromDashboard(dashboard, 'r1')).toEqual({ authored: [], followed: [] })
    expect(removeRoadmapFromProfile(profile, 'r1')?.roadmaps).toEqual([])
  })
})
