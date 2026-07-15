import { screen } from '@testing-library/react'

import { buildAuthUser, buildAuthValue, renderWithAuth } from '@/test/auth-harness'
import { TopBar } from './TopBar'

const AUTHENTICATED = buildAuthValue({ status: 'authenticated', user: buildAuthUser() })

describe('TopBar', () => {
  it('renders the wordmark on the left and Dashboard / Profile / avatar menu on the right', () => {
    renderWithAuth(<TopBar />, { authValue: AUTHENTICATED })

    expect(screen.getByRole('link', { name: 'Wren home' })).toBeInTheDocument()

    const dashboard = screen.getByRole('link', { name: 'Dashboard' })
    expect(dashboard).toHaveAttribute('href', '/dashboard')

    const profile = screen.getByRole('link', { name: 'Profile' })
    expect(profile).toHaveAttribute('href', '/user/ada')

    expect(screen.getByRole('button', { name: 'Open account menu' })).toBeInTheDocument()
  })

  it('sits on a card surface with a hairline bottom border and no sidebar', () => {
    const { container } = renderWithAuth(<TopBar />, { authValue: AUTHENTICATED })

    const header = container.querySelector('header')
    expect(header).toHaveClass('bg-card', 'border-b', 'border-border')
    expect(container.querySelector('aside')).toBeNull()
  })

  it('hides the personal Dashboard / Profile links when anonymous', () => {
    renderWithAuth(<TopBar />, { authValue: buildAuthValue({ status: 'anonymous' }) })

    expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Profile' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Log in' })).toBeInTheDocument()
  })
})
