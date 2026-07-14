import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

import { TopBar } from './TopBar'

describe('TopBar', () => {
  it('renders the wordmark on the left and Dashboard / Profile / avatar menu on the right', () => {
    render(
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Wren home' })).toBeInTheDocument()

    const dashboard = screen.getByRole('link', { name: 'Dashboard' })
    expect(dashboard).toHaveAttribute('href', '/dashboard')

    const profile = screen.getByRole('link', { name: 'Profile' })
    expect(profile).toHaveAttribute('href', '/profile')

    expect(
      screen.getByRole('button', { name: 'Open account menu' }),
    ).toBeInTheDocument()
  })

  it('sits on a card surface with a hairline bottom border and no sidebar', () => {
    const { container } = render(
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>,
    )

    const header = container.querySelector('header')
    expect(header).toHaveClass('bg-card', 'border-b', 'border-border')
    expect(container.querySelector('aside')).toBeNull()
  })
})
