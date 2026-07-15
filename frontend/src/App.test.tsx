import { render, screen } from '@testing-library/react'

import { App } from './App'

describe('App routing', () => {
  it('routes / to the landing view inside the app shell', async () => {
    render(<App />)

    // The shell wraps every view: the wordmark is always present. Awaited so the
    // AuthProvider's mount-time session resume settles inside act().
    expect(await screen.findByRole('link', { name: 'Wren home' })).toBeInTheDocument()

    // / resolves to the landing hero.
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: /learn anything, in the right order/i,
      }),
    ).toBeInTheDocument()
  })
})
