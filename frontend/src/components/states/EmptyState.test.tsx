import { render, screen } from '@testing-library/react'

import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('renders the Fraunces title, sub-line, and a single action', () => {
    render(
      <EmptyState
        title="Nothing here yet."
        description="Start your first roadmap."
        action={<a href="/x">Get started</a>}
      />,
    )
    expect(screen.getByText('Nothing here yet.')).toHaveClass('display-m')
    expect(screen.getByText('Start your first roadmap.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Get started' })).toHaveAttribute('href', '/x')
  })

  it('omits the sub-line and action when not provided', () => {
    render(<EmptyState title="No published roadmaps yet." />)
    expect(screen.getByText('No published roadmaps yet.')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})
