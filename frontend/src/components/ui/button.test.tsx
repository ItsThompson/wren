import { render, screen } from '@testing-library/react'

import { Button } from './button'

describe('Button', () => {
  it('renders the primary variant as a terracotta fill with a cream label', () => {
    // The design contract: primary = terracotta fill (--primary),
    // cream label (--primary-foreground). Tailwind expresses this via tokens.
    render(<Button>Start a roadmap</Button>)

    const button = screen.getByRole('button', { name: 'Start a roadmap' })
    expect(button).toHaveClass('bg-primary', 'text-primary-foreground')
  })

  it('renders the secondary variant with the secondary fill', () => {
    render(<Button variant="secondary">Browse</Button>)

    expect(screen.getByRole('button', { name: 'Browse' })).toHaveClass(
      'bg-secondary',
      'text-secondary-foreground',
    )
  })

  it('renders as the child element when asChild is set', () => {
    render(
      <Button asChild>
        <a href="/somewhere">Go</a>
      </Button>,
    )

    const link = screen.getByRole('link', { name: 'Go' })
    expect(link).toHaveAttribute('href', '/somewhere')
    expect(link).toHaveClass('bg-primary')
  })
})
