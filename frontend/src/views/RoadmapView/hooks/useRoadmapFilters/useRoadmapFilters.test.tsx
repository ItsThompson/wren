import { act, renderHook } from '@testing-library/react'

import type { Roadmap } from '../../types'
import { useRoadmapFilters } from './useRoadmapFilters'

function buildRoadmap(tags: string[][]): Roadmap {
  const subsections = Object.fromEntries(
    tags.map((subsectionTags, index) => {
      const id = `sub-${index}`
      return [
        id,
        {
          id,
          title: id,
          tags: subsectionTags,
          prereq_ids: [],
          resource_order: [],
          resources: {},
          item_order: [],
          checklist_items: {},
        },
      ]
    }),
  )
  const subsectionOrder = Object.keys(subsections)
  return {
    id: 'roadmap',
    owner: 'owner',
    title: 'Roadmap',
    subject_tags: [],
    published_visibility: 'public',
    status: 'published',
    revision: 1,
    section_order: ['section'],
    suggested_path: [],
    sections: {
      section: {
        id: 'section',
        title: 'Section',
        subsection_order: subsectionOrder,
        subsections,
      },
    },
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

describe('useRoadmapFilters', () => {
  it('starts in ANY mode with every topic shown', () => {
    const { result } = renderHook(() => useRoadmapFilters(buildRoadmap([['a'], ['b']])))

    expect(result.current.state.matchMode).toBe('any')
    expect(result.current.state.selectedTags).toEqual(new Set())
    expect(result.current.state.matchingSubsectionIds).toBeNull()
    expect(result.current.state.shownTopicCount).toBe(2)
  })

  it('supports independent selection, mode changes, and clear without losing mode', () => {
    const { result } = renderHook(() => useRoadmapFilters(buildRoadmap([['a'], ['b'], ['a', 'b']])))

    act(() => result.current.actions.toggleTag('a'))
    act(() => result.current.actions.toggleTag('b'))
    expect(result.current.state.selectedTags).toEqual(new Set(['a', 'b']))
    expect(result.current.state.shownTopicCount).toBe(3)

    act(() => result.current.actions.setMatchMode('all'))
    expect(result.current.state.shownTopicCount).toBe(1)
    expect(result.current.state.matchingSubsectionIds).toEqual(new Set(['sub-2']))

    act(() => result.current.actions.toggleTag('a'))
    expect(result.current.state.selectedTags).toEqual(new Set(['b']))
    expect(result.current.state.shownTopicCount).toBe(2)

    act(() => result.current.actions.clearFilters())
    expect(result.current.state.selectedTags).toEqual(new Set())
    expect(result.current.state.matchMode).toBe('all')
    expect(result.current.state.matchingSubsectionIds).toBeNull()
  })

  it('ignores unavailable tags and reconciles selections when the roadmap changes', () => {
    const firstRoadmap = buildRoadmap([['a'], ['b']])
    const { result, rerender } = renderHook(({ roadmap }) => useRoadmapFilters(roadmap), {
      initialProps: { roadmap: firstRoadmap },
    })

    act(() => result.current.actions.toggleTag('a'))
    act(() => result.current.actions.toggleTag('missing'))
    expect(result.current.state.selectedTags).toEqual(new Set(['a']))

    rerender({ roadmap: buildRoadmap([['b'], ['c']]) })
    expect(result.current.state.selectedTags).toEqual(new Set())
    expect(result.current.state.shownTopicCount).toBe(2)
  })
})
