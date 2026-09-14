import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import type { RoadmapFilterActions, RoadmapFilterState } from '../types'
import { RoadmapFilterPanel } from './RoadmapFilterPanel'

function buildState(overrides: Partial<RoadmapFilterState> = {}): RoadmapFilterState {
  return {
    availableTags: ['arrays', 'hashing'],
    selectedTags: new Set(),
    matchMode: 'any',
    matchingSubsectionIds: null,
    shownTopicCount: 3,
    totalTopicCount: 3,
    ...overrides,
  }
}

function buildActions(): RoadmapFilterActions {
  return {
    toggleTag: vi.fn(),
    setMatchMode: vi.fn(),
    clearFilters: vi.fn(),
  }
}

describe('RoadmapFilterPanel', () => {
  it('renders accessible controls and selected chip states', () => {
    const state = buildState({ selectedTags: new Set(['arrays']) })
    render(<RoadmapFilterPanel state={state} actions={buildActions()} />)

    const panel = screen.getByRole('group', { name: 'Roadmap filters' })
    expect(within(panel).getByText('Showing 3 of 3 topics')).toBeInTheDocument()
    const selectedChip = within(panel).getByRole('button', { name: 'arrays' })
    const unselectedChip = within(panel).getByRole('button', { name: 'hashing' })
    expect(selectedChip).toHaveAttribute('aria-pressed', 'true')
    expect(selectedChip).toHaveClass('border-accent')
    expect(selectedChip.style.getPropertyValue('--tag-hue')).not.toBe('')
    expect(unselectedChip).toHaveAttribute('aria-pressed', 'false')
    expect(unselectedChip).toHaveClass('border-transparent')
    expect(unselectedChip.style.getPropertyValue('--tag-hue')).not.toBe('')
    expect(within(panel).getByRole('button', { name: 'Clear filters' })).toBeEnabled()
  })

  it('keeps tag styling when a chip becomes selected and adds only an outline', () => {
    const { rerender } = render(<RoadmapFilterPanel state={buildState()} actions={buildActions()} />)
    const unselectedChip = screen.getByRole('button', { name: 'arrays' })
    const initialStyle = {
      hue: unselectedChip.style.getPropertyValue('--tag-hue'),
      backgroundColor: unselectedChip.style.backgroundColor,
      color: unselectedChip.style.color,
    }

    rerender(
      <RoadmapFilterPanel state={buildState({ selectedTags: new Set(['arrays']) })} actions={buildActions()} />,
    )

    const selectedChip = screen.getByRole('button', { name: 'arrays' })
    expect(selectedChip).toHaveClass('border-accent')
    expect(selectedChip.style.getPropertyValue('--tag-hue')).toBe(initialStyle.hue)
    expect(selectedChip.style.backgroundColor).toBe(initialStyle.backgroundColor)
    expect(selectedChip.style.color).toBe(initialStyle.color)
  })

  it('forwards chip and mode actions without allowing an empty mode', async () => {
    const user = userEvent.setup()
    const actions = buildActions()
    const { rerender } = render(<RoadmapFilterPanel state={buildState()} actions={actions} />)

    const panel = screen.getByRole('group', { name: 'Roadmap filters' })
    await user.click(within(panel).getByRole('button', { name: 'arrays' }))
    expect(actions.toggleTag).toHaveBeenCalledWith('arrays')

    await user.click(within(panel).getByRole('radio', { name: 'ANY' }))
    expect(actions.setMatchMode).not.toHaveBeenCalled()
    await user.click(within(panel).getByRole('radio', { name: 'ALL' }))
    expect(actions.setMatchMode).toHaveBeenCalledWith('all')
    rerender(<RoadmapFilterPanel state={buildState({ matchMode: 'all' })} actions={actions} />)
    await user.click(screen.getByRole('radio', { name: 'ALL' }))
    expect(actions.setMatchMode).toHaveBeenCalledTimes(1)
  })

  it('does not render for a roadmap without track tags', () => {
    const state = buildState({ availableTags: [] })
    render(<RoadmapFilterPanel state={state} actions={buildActions()} />)

    expect(screen.queryByRole('group', { name: 'Roadmap filters' })).not.toBeInTheDocument()
  })
})
