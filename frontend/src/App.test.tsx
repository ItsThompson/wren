import { render, screen } from '@testing-library/react'

import { App } from './App'

describe('App routing', () => {
  it('routes / to the landing view inside the app shell', () => {
    render(<App />)

    // The shell wraps every view: the wordmark is always present.
    expect(screen.getByRole('link', { name: 'Wren home' })).toBeInTheDocument()

    // / resolves to the landing hero.
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: /learn anything, in the right order/i,
      }),
    ).toBeInTheDocument()
  })
})
