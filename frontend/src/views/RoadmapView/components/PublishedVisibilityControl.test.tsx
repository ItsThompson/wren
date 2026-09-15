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

  it('emits public when the private draft control is pressed', async () => {
    const user = userEvent.setup()
    const { onChange } = renderControl({ status: 'draft', publishedVisibility: 'private' })
    const button = screen.getByRole('button', { name: 'Public when published' })
    expect(button).toHaveAttribute('aria-pressed', 'false')
    await user.click(button)
    expect(onChange).toHaveBeenCalledWith('public')
  })

  it.each([
    ['published', 'public', 'Public access', 'true', 'Anyone with the link can read this roadmap.'],
    ['published', 'private', 'Private access', 'false', 'Only you can read this roadmap.'],
    [
      'archived',
      'public',
      'Public access',
      'true',
      'Anyone with the link can read this roadmap. It is hidden from discovery.',
    ],
  ] as const)('describes %s %s state', (status, visibility, label, pressed, helper) => {
    renderControl({ status, publishedVisibility: visibility })
    expect(screen.getByRole('button', { name: label })).toHaveAttribute('aria-pressed', pressed)
    expect(screen.getByText(helper)).toBeInTheDocument()
  })

  it('disables the control while saving or when disabled', () => {
    const { rerender } = renderControl({ saving: true })
    expect(screen.getByRole('button')).toBeDisabled()
    expect(screen.getByRole('button')).toHaveTextContent('Saving…')

    rerender(
      <PublishedVisibilityControl
        status="published"
        publishedVisibility="public"
        saving={false}
        disabled
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('describes current access for archived private roadmaps', () => {
    renderControl({ status: 'archived', publishedVisibility: 'private' })
    expect(screen.getByRole('button', { name: 'Private access' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText('Only you can read this roadmap. It is hidden from discovery.')).toBeInTheDocument()
  })
})
