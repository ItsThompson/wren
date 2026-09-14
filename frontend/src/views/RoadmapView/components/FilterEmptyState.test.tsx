import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { FilterEmptyState } from './FilterEmptyState'

describe('FilterEmptyState', () => {
  it('shows the calm no-results message and clears filters', async () => {
    const user = userEvent.setup()
    const onClear = vi.fn()
    render(<FilterEmptyState onClear={onClear} />)

    expect(screen.getByRole('heading', { name: 'No topics match these filters' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(onClear).toHaveBeenCalledOnce()
  })
})
