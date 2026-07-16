import { render, screen } from '@testing-library/react'

import { ErrorState } from './ErrorState'

describe('ErrorState', () => {
  it('renders a title as an alert with a recovery action', () => {
    render(
      <ErrorState
        title="Roadmap not found"
        description="This roadmap does not exist or is not shared with you."
        action={<button type="button">Try again</button>}
      />,
    )
    // role="alert" carries meaning to assistive tech (never color alone).
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Roadmap not found')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
