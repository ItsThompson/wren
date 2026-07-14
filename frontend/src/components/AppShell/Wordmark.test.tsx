import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

import { Wordmark } from './Wordmark'

describe('Wordmark', () => {
  it('renders the lowercase Fraunces wren wordmark linking home', () => {
    render(
      <MemoryRouter>
        <Wordmark />
      </MemoryRouter>,
    )

    const link = screen.getByRole('link', { name: 'Wren home' })
    expect(link).toHaveTextContent('wren')
    expect(link).toHaveAttribute('href', '/')
    // Fraunces is the serif face wired to --font-serif; wordmark is the one
    // place the brand signs its name in the display serif.
    expect(link).toHaveClass('font-serif', 'lowercase')
  })
})
