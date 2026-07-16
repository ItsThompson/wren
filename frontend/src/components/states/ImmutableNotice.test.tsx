import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ImmutableNotice } from './ImmutableNotice'

describe('ImmutableNotice', () => {
  it('offers a fork action and explains why in text', async () => {
    const user = userEvent.setup()
    const onFork = vi.fn()
    render(<ImmutableNotice onFork={onFork} />)

    expect(screen.getByRole('alert')).toHaveTextContent(/fork it to make changes/i)
    await user.click(screen.getByRole('button', { name: 'Fork to change' }))
    expect(onFork).toHaveBeenCalledTimes(1)
  })

  it('disables and relabels the action while forking', () => {
    render(<ImmutableNotice onFork={vi.fn()} forking />)
    expect(screen.getByRole('button', { name: 'Forking…' })).toBeDisabled()
  })

  it('renders without an action when no fork handler is given', () => {
    render(<ImmutableNotice />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
