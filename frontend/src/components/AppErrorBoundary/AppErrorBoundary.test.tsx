import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AppErrorBoundary } from './AppErrorBoundary'

function BrokenChild(): null {
  if (typeof document === 'object') throw new Error('render failed')
  return null
}

describe('AppErrorBoundary', () => {
  it('renders a recoverable fallback when a child throws during render', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <AppErrorBoundary>
        <BrokenChild />
      </AppErrorBoundary>,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    consoleError.mockRestore()
  })
})
