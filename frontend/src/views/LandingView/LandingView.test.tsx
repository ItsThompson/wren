import { render, screen } from '@testing-library/react'

import { LandingView } from './LandingView'

describe('LandingView', () => {
  it('renders a Fraunces display-xl hero on bone', () => {
    render(<LandingView />)

    const hero = screen.getByRole('heading', {
      level: 1,
      name: /learn anything, in the right order/i,
    })
    // display-xl is the Fraunces landing-hero moment.
    expect(hero).toHaveClass('display-xl')
  })

  it('renders one terracotta primary CTA (fill + cream label)', () => {
    render(<LandingView />)

    const cta = screen.getByRole('button', { name: /start a roadmap/i })
    expect(cta).toHaveClass('bg-primary', 'text-primary-foreground')
  })
})
