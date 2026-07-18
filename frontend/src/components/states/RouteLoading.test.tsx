import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RouteLoading } from './RouteLoading'

describe('RouteLoading', () => {
  it('renders an accessible loading status', () => {
    render(<RouteLoading />)

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument()
  })
})
