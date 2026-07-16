import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import type { components } from '@/api'
import { RoadmapCardGrid } from './RoadmapCardGrid'

type RoadmapCardData = components['schemas']['RoadmapCard']

function buildCard(overrides: Partial<RoadmapCardData> = {}): RoadmapCardData {
  return {
    id: 'grokking-dsa-7f3k',
    title: 'Grokking DSA',
    status: 'published',
    visibility: 'public',
    subject_tags: [],
    ...overrides,
  }
}

function renderGrid(roadmaps: RoadmapCardData[]) {
  return render(
    <MemoryRouter>
      <RoadmapCardGrid roadmaps={roadmaps} />
    </MemoryRouter>,
  )
}

describe('RoadmapCardGrid', () => {
  it('renders one linked card per roadmap, each pointing at its own roadmap', () => {
    renderGrid([
      buildCard({ id: 'dsa-1', title: 'Grokking DSA' }),
      buildCard({ id: 'sys-2', title: 'System Design' }),
    ])

    const cards = screen.getAllByRole('link')
    expect(cards).toHaveLength(2)
    expect(screen.getByRole('link', { name: /Grokking DSA/ })).toHaveAttribute(
      'href',
      '/roadmaps/dsa-1',
    )
    expect(screen.getByRole('link', { name: /System Design/ })).toHaveAttribute(
      'href',
      '/roadmaps/sys-2',
    )
  })

  it('wraps each card in its own list item so the grid is a semantic list', () => {
    const { container } = renderGrid([
      buildCard({ id: 'dsa-1', title: 'Grokking DSA' }),
      buildCard({ id: 'sys-2', title: 'System Design' }),
    ])

    expect(container.querySelectorAll('ul > li')).toHaveLength(2)
  })

  it('renders an empty grid with no cards when there are no roadmaps', () => {
    renderGrid([])
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})
