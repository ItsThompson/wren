import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'

import { AvatarMenu } from './AvatarMenu'

describe('AvatarMenu', () => {
  it('is closed until the avatar trigger is clicked', () => {
    render(
      <MemoryRouter>
        <AvatarMenu />
      </MemoryRouter>,
    )

    expect(
      screen.getByRole('button', { name: 'Open account menu' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument()
  })

  it('opens the menu and links each item to its account destination', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <AvatarMenu />
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: 'Open account menu' }))

    const dashboard = await screen.findByRole('menuitem', { name: /dashboard/i })
    expect(dashboard).toHaveAttribute('href', '/dashboard')

    const profile = screen.getByRole('menuitem', { name: /your profile/i })
    expect(profile).toHaveAttribute('href', '/profile')
  })
})
