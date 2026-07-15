import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import { DagNodeCard } from './DagNodeCard'
import { NODE_STATE, type NodeState } from '../types'

function renderCard(state: NodeState, title = 'Arrays & two pointers') {
  return render(
    <MemoryRouter>
      <DagNodeCard title={title} state={state} href={`/roadmaps/rm-1#sub_${state}`} />
    </MemoryRouter>,
  )
}

describe('DagNodeCard', () => {
  it('renders each node as a real link to the subsection in the list view', () => {
    renderCard(NODE_STATE.Available)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/roadmaps/rm-1#sub_available')
  })

  it('conveys state by an accessible label and a stable data-state hook, not color alone', () => {
    renderCard(NODE_STATE.Locked)
    const link = screen.getByRole('link', { name: /Arrays & two pointers \(locked\)/ })
    expect(link).toHaveAttribute('data-state', NODE_STATE.Locked)
  })

  it('renders a distinct icon per state (color + icon)', () => {
    const done = renderCard(NODE_STATE.Done)
    const doneIcon = done.container.querySelector('a svg')
    done.unmount()

    const available = renderCard(NODE_STATE.Available)
    const availableIcon = available.container.querySelector('a svg')
    available.unmount()

    const locked = renderCard(NODE_STATE.Locked)
    const lockedIcon = locked.container.querySelector('a svg')

    // Each state renders an icon, and the three icons differ (distinct shapes).
    const classes = [doneIcon, availableIcon, lockedIcon].map((icon) => icon?.getAttribute('class'))
    expect(classes.every((className) => Boolean(className))).toBe(true)
    expect(new Set(classes).size).toBe(3)
  })

  it('keeps a locked node clickable (no gating): it is a live link, not disabled', () => {
    renderCard(NODE_STATE.Locked)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href')
    expect(link).not.toHaveAttribute('aria-disabled', 'true')
  })

  it('renders no progress bar on a node', () => {
    renderCard(NODE_STATE.Done)
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })
})
