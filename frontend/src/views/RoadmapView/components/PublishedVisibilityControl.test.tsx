import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PublishedVisibilityControl } from './PublishedVisibilityControl'

function renderControl(overrides: Partial<Parameters<typeof PublishedVisibilityControl>[0]> = {}) {
  const props = {
    status: 'draft' as const,
    publishedVisibility: 'public' as const,
    saving: false,
    disabled: false,
    onChange: vi.fn(),
    ...overrides,
  }
  return { ...render(<PublishedVisibilityControl {...props} />), onChange: props.onChange }
}

describe('PublishedVisibilityControl', () => {
  it('describes the draft future state and exposes its pressed state', () => {
    renderControl()
    expect(screen.getByRole('button', { name: 'Public when published' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Drafts remain private until you publish this roadmap.')).toBeInTheDocument()
  })

  it('emits private when the public draft control is pressed', async () => {
    const user = userEvent.setup()
    const { onChange } = renderControl()
    await user.click(screen.getByRole('button', { name: 'Public when published' }))
    expect(onChange).toHaveBeenCalledWith('private')
  })

  it('describes current access for archived roadmaps', () => {
    renderControl({ status: 'archived', publishedVisibility: 'private' })
    expect(screen.getByRole('button', { name: 'Private access' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText('Only you can read this roadmap. It is hidden from discovery.')).toBeInTheDocument()
  })
})
