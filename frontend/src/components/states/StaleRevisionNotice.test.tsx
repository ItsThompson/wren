import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { StaleRevisionNotice } from './StaleRevisionNotice'

describe('StaleRevisionNotice', () => {
  it('surfaces an ochre re-read prompt with a reload action (color AND text)', async () => {
    const user = userEvent.setup()
    const onReload = vi.fn()
    render(<StaleRevisionNotice onReload={onReload} />)

    const alert = screen.getByRole('alert')
    // Meaning is in the text, not just the ochre surface.
    expect(alert).toHaveTextContent(/reload to continue/i)
    // The ochre reinforcement is present on the surface classes.
    expect(alert.className).toMatch(/warning/)

    await user.click(screen.getByRole('button', { name: 'Reload' }))
    expect(onReload).toHaveBeenCalledTimes(1)
  })

  it('shows the server detail when provided', () => {
    render(<StaleRevisionNotice detail="Revision 12 -> 13; re-read." onReload={vi.fn()} />)
    expect(screen.getByText('Revision 12 -> 13; re-read.')).toBeInTheDocument()
  })
})
