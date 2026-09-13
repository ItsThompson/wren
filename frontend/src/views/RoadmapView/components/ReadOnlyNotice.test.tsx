import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import { ReadOnlyNotice } from './ReadOnlyNotice'

describe('ReadOnlyNotice', () => {
  it('links anonymous readers to login', () => {
    render(
      <MemoryRouter>
        <ReadOnlyNotice />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Log in to track progress' })).toHaveAttribute('href', '/auth')
  })
})
