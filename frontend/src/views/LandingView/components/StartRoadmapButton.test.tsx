import { screen } from '@testing-library/react'

import { buildAuthUser, buildAuthValue, renderWithAuth } from '@/test/auth-harness'
import { StartRoadmapButton } from './StartRoadmapButton'

describe('StartRoadmapButton', () => {
  it('links an anonymous visitor to signup in register mode, styled as the primary CTA', () => {
    renderWithAuth(<StartRoadmapButton />, { authValue: buildAuthValue({ status: 'anonymous' }) })

    const cta = screen.getByRole('link', { name: /start a roadmap/i })
    expect(cta).toHaveAttribute('href', '/auth?mode=register')
    // asChild renders the Slot styling onto the anchor (VC1).
    expect(cta).toHaveClass('bg-primary', 'text-primary-foreground')
  })

  it('links an authenticated visitor to the dashboard', () => {
    renderWithAuth(<StartRoadmapButton />, {
      authValue: buildAuthValue({ status: 'authenticated', user: buildAuthUser() }),
    })

    expect(screen.getByRole('link', { name: /start a roadmap/i })).toHaveAttribute(
      'href',
      '/dashboard',
    )
  })

  it('renders a disabled control with no link while the session is resolving', () => {
    renderWithAuth(<StartRoadmapButton />, { authValue: buildAuthValue({ status: 'loading' }) })

    expect(screen.getByRole('button', { name: /start a roadmap/i })).toBeDisabled()
    expect(screen.queryByRole('link', { name: /start a roadmap/i })).not.toBeInTheDocument()
  })
})
