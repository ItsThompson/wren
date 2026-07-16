import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { InlineNotice } from './InlineNotice'

describe('InlineNotice', () => {
  it('renders a polite status message and a dismiss control', async () => {
    const user = userEvent.setup()
    const onDismiss = vi.fn()
    render(<InlineNotice onDismiss={onDismiss}>We couldn’t save your progress.</InlineNotice>)

    expect(screen.getByRole('status')).toHaveTextContent('We couldn’t save your progress.')
    await user.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})
