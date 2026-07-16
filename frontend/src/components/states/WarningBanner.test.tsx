import { render, screen } from '@testing-library/react'

import { WarningBanner } from './WarningBanner'

describe('WarningBanner', () => {
  it('announces the title as an alert on the ochre surface (color AND text)', () => {
    render(<WarningBanner title="Something needs your attention." />)

    const alert = screen.getByRole('alert')
    // Meaning is in the text, not just the ochre surface.
    expect(alert).toHaveTextContent('Something needs your attention.')
    // The ochre reinforcement is present on the surface classes.
    expect(alert.className).toMatch(/warning/)
  })

  it('renders supporting copy when provided', () => {
    render(
      <WarningBanner title="Heads up.">Here is some more detail about the state.</WarningBanner>,
    )
    expect(screen.getByText('Here is some more detail about the state.')).toBeInTheDocument()
  })

  it('renders a recovery action when provided', () => {
    render(<WarningBanner title="Heads up." action={<button type="button">Do it</button>} />)
    expect(screen.getByRole('button', { name: 'Do it' })).toBeInTheDocument()
  })

  it('omits supporting copy and action when not provided', () => {
    render(<WarningBanner title="Just a title." />)
    expect(screen.getByRole('alert')).toHaveTextContent('Just a title.')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
