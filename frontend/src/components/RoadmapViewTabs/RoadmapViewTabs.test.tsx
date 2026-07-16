import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import { RoadmapViewTabs } from './RoadmapViewTabs'

function renderTabs(active: 'list' | 'tree') {
  return render(
    <MemoryRouter>
      <RoadmapViewTabs roadmapId="grokking-dsa-7f3k" active={active} />
    </MemoryRouter>,
  )
}

describe('RoadmapViewTabs', () => {
  it('marks List as the current page and links Tree when the list view is active', () => {
    renderTabs('list')

    const current = screen.getByText('List')
    expect(current).toHaveAttribute('aria-current', 'page')
    expect(current.tagName).toBe('SPAN')

    const treeLink = screen.getByRole('link', { name: 'Tree' })
    expect(treeLink).toHaveAttribute('href', '/roadmaps/grokking-dsa-7f3k/tree')
    expect(screen.queryByRole('link', { name: 'List' })).not.toBeInTheDocument()
  })

  it('marks Tree as the current page and links List when the tree view is active', () => {
    renderTabs('tree')

    const current = screen.getByText('Tree')
    expect(current).toHaveAttribute('aria-current', 'page')
    expect(current.tagName).toBe('SPAN')

    const listLink = screen.getByRole('link', { name: 'List' })
    expect(listLink).toHaveAttribute('href', '/roadmaps/grokking-dsa-7f3k')
    expect(screen.queryByRole('link', { name: 'Tree' })).not.toBeInTheDocument()
  })

  it('exposes the switcher as a labelled navigation landmark', () => {
    renderTabs('list')
    expect(screen.getByRole('navigation', { name: 'Roadmap views' })).toBeInTheDocument()
  })
})
