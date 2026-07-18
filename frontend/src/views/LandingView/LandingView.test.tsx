import { screen } from '@testing-library/react'

import { buildAuthUser, buildAuthValue, renderWithAuth } from '@/test/auth-harness'
import { CTA_SETUP_MICROCOPY, FAQ_ITEMS, VALUE_FOOTNOTE, VALUE_PULL_QUOTE } from './constants'
import { LandingView } from './LandingView'

describe('LandingView', () => {
  it('renders the single Fraunces display-xl hero on bone', () => {
    renderWithAuth(<LandingView />)

    const hero = screen.getByRole('heading', {
      level: 1,
      name: /learn anything, in the right order/i,
    })
    // display-xl is the page's ONE Fraunces moment; nothing else uses it.
    expect(hero).toHaveClass('display-xl')
    expect(document.querySelectorAll('.display-xl')).toHaveLength(1)
  })

  it('keeps the value pull-quote in the grotesque scale (not a second serif moment)', () => {
    renderWithAuth(<LandingView />)

    const pullQuote = screen.getByText(VALUE_PULL_QUOTE)
    expect(pullQuote).not.toHaveClass('font-serif')
    expect(pullQuote.className).not.toMatch(/display-/)
  })

  it('mentions the zone of proximal development without the "learning scientists call this" framing', () => {
    renderWithAuth(<LandingView />)

    expect(screen.getByText(VALUE_FOOTNOTE)).toBeInTheDocument()
    expect(screen.queryByText(/learning scientists call this/i)).not.toBeInTheDocument()
  })

  it('lets FAQ answers span the full FAQ row width', () => {
    renderWithAuth(<LandingView />)

    const answer = screen.getByText(FAQ_ITEMS[0].answer)
    expect(answer).toHaveClass('w-full')
    expect(answer).not.toHaveClass('max-w-[64ch]')
  })

  it('spreads footer content across a responsive grid', () => {
    renderWithAuth(<LandingView />)

    expect(screen.getByRole('contentinfo')).toHaveClass('grid', 'sm:grid-cols-3')
  })

  it('AC8: the hero shows subordinate connect-your-agent setup microcopy near the CTA', () => {
    renderWithAuth(<LandingView />)
    expect(screen.getByText(CTA_SETUP_MICROCOPY)).toBeInTheDocument()
  })

  it('AC5: the subhead names the product category in plain language', () => {
    renderWithAuth(<LandingView />)
    expect(screen.getByText(/learning-roadmap tool/i)).toBeInTheDocument()
  })

  it('AC7: the hero shows an authentic roadmap image with meaningful alt text', () => {
    renderWithAuth(<LandingView />)
    const image = screen.getByRole('img')
    expect(image).toHaveAttribute('src', '/landing/roadmap-tree.png')
    expect(image.getAttribute('alt')).toMatch(/prerequisite graph/i)
  })

  it('AC1: a logged-out visitor gets a terracotta CTA link to signup (register mode)', () => {
    renderWithAuth(<LandingView />, { authValue: buildAuthValue({ status: 'anonymous' }) })

    const ctas = screen.getAllByRole('link', { name: /start a roadmap/i })
    // AC6/repetition: the primary CTA appears in the hero AND the final band.
    expect(ctas).toHaveLength(2)
    for (const cta of ctas) {
      expect(cta).toHaveAttribute('href', '/auth?mode=register')
    }
    // AC3 + adapted terracotta assertion: real link carrying the primary fill.
    expect(ctas[0]).toHaveClass('bg-primary', 'text-primary-foreground')
  })

  it('AC2: a logged-in visitor gets a CTA link to the dashboard', () => {
    renderWithAuth(<LandingView />, {
      authValue: buildAuthValue({ status: 'authenticated', user: buildAuthUser() }),
    })

    for (const cta of screen.getAllByRole('link', { name: /start a roadmap/i })) {
      expect(cta).toHaveAttribute('href', '/dashboard')
    }
  })

  it('renders a disabled CTA (no signup link) while the session is resolving', () => {
    renderWithAuth(<LandingView />, { authValue: buildAuthValue({ status: 'loading' }) })

    const ctas = screen.getAllByRole('button', { name: /start a roadmap/i })
    expect(ctas).toHaveLength(2)
    for (const cta of ctas) {
      expect(cta).toBeDisabled()
    }
    expect(screen.queryByRole('link', { name: /start a roadmap/i })).not.toBeInTheDocument()
  })

  it('AC4: no dead "Browse examples" control remains', () => {
    renderWithAuth(<LandingView />)
    expect(screen.queryByText(/browse examples/i)).not.toBeInTheDocument()
  })

  it('AC6: the below-fold explainer sections all render', () => {
    renderWithAuth(<LandingView />)

    // How it works: heading + all three steps.
    expect(screen.getByRole('heading', { name: /how it works/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Connect your AI agent' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Get a roadmap built for you' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Learn in the right order' })).toBeInTheDocument()

    // Dual audience: the two tracks (exact names; "For you" is a prefix of
    // "For your AI agent", so a substring regex would match both).
    expect(screen.getByRole('heading', { name: 'For you' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'For your AI agent' })).toBeInTheDocument()

    // FAQ: the two required questions.
    expect(screen.getByRole('heading', { name: /do i need to be technical\?/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /what's the ai-agent part\?/i })).toBeInTheDocument()
  })
})
