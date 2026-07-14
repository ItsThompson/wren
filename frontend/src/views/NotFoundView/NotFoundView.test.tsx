import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

import { NotFoundView } from './NotFoundView'

describe('NotFoundView', () => {
  it('renders the empty-state message and a link back home', () => {
    render(
      <MemoryRouter>
        <NotFoundView />
      </MemoryRouter>,
    )

    expect(screen.getByText(/this page/i)).toBeInTheDocument()
    expect(
      screen.getByText(/doesn.t exist yet/i),
    ).toBeInTheDocument()

    const back = screen.getByRole('link', { name: /back to wren/i })
    expect(back).toHaveAttribute('href', '/')
  })
})
