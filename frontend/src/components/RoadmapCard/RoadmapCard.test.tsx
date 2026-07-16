import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import type { components } from '@/api'
import { RoadmapCard } from './RoadmapCard'

type RoadmapCardData = components['schemas']['RoadmapCard']

function buildCard(overrides: Partial<RoadmapCardData> = {}): RoadmapCardData {
  return {
    id: 'grokking-dsa-7f3k',
    title: 'Grokking DSA',
    status: 'published',
    visibility: 'public',
    subject_tags: ['cs', 'interview-prep'],
    ...overrides,
  }
}

function renderCard(overrides: Partial<RoadmapCardData> = {}) {
  return render(
    <MemoryRouter>
      <RoadmapCard roadmap={buildCard(overrides)} />
    </MemoryRouter>,
  )
}

describe('RoadmapCard', () => {
  it('links to the roadmap view and shows the title and subject tags', () => {
    renderCard()
    expect(screen.getByRole('link', { name: /Grokking DSA/ })).toHaveAttribute(
      'href',
      '/roadmaps/grokking-dsa-7f3k',
    )
    expect(screen.getByText('cs')).toBeInTheDocument()
    expect(screen.getByText('interview-prep')).toBeInTheDocument()
  })

  it('renders the Published status and Public visibility badges by label', () => {
    renderCard({ status: 'published', visibility: 'public' })
    expect(screen.getByText('Published')).toBeInTheDocument()
    expect(screen.getByText('Public')).toBeInTheDocument()
  })

  it('renders the Draft status and Private visibility badges by label', () => {
    renderCard({ status: 'draft', visibility: 'private' })
    expect(screen.getByText('Draft')).toBeInTheDocument()
    expect(screen.getByText('Private')).toBeInTheDocument()
  })

  it('renders the Archived status badge', () => {
    renderCard({ status: 'archived' })
    expect(screen.getByText('Archived')).toBeInTheDocument()
  })

  it('omits the subject-tag list when there are no tags', () => {
    renderCard({ subject_tags: [] })
    expect(screen.queryByText('cs')).not.toBeInTheDocument()
  })
})
