import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Toggle } from './toggle'

describe('Toggle', () => {
  it('exposes pressed state and toggles on activation', async () => {
    const user = userEvent.setup()
    render(<Toggle aria-label="Favorite" />)

    const toggle = screen.getByRole('button', { name: 'Favorite' })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
  })

  it('keeps a controlled pressed state and honors disabled behavior', async () => {
    const user = userEvent.setup()
    const onPressedChange = vi.fn()
    render(<Toggle aria-label="Favorite" pressed disabled onPressedChange={onPressedChange} />)

    const toggle = screen.getByRole('button', { name: 'Favorite' })
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
    await user.click(toggle)
    expect(onPressedChange).not.toHaveBeenCalled()
    expect(toggle).toBeDisabled()
  })
})
