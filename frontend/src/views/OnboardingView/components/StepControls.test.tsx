import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { StepControls } from './StepControls'

interface Overrides {
  onContinue?: () => void
  onBack?: () => void
  onSkip?: () => void
  isFirstStep?: boolean
  isLastStep?: boolean
  isSubmitting?: boolean
  error?: string | null
  continueLabel?: string
}

function renderControls(overrides: Overrides = {}) {
  render(
    <StepControls
      onContinue={overrides.onContinue ?? vi.fn()}
      onBack={overrides.onBack ?? vi.fn()}
      onSkip={overrides.onSkip ?? vi.fn()}
      isFirstStep={overrides.isFirstStep ?? false}
      isLastStep={overrides.isLastStep ?? false}
      isSubmitting={overrides.isSubmitting ?? false}
      error={overrides.error ?? null}
      continueLabel={overrides.continueLabel ?? 'Continue'}
    />,
  )
}

describe('StepControls', () => {
  it('shows the primary label, Back, and Skip on a middle step', () => {
    renderControls({ continueLabel: 'Continue' })

    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Skip' })).toBeInTheDocument()
  })

  it('hides Back on the first step', () => {
    renderControls({ isFirstStep: true })

    expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument()
  })

  it('renders the given primary label (e.g. the final step)', () => {
    renderControls({ isLastStep: true, continueLabel: 'Get started' })

    expect(screen.getByRole('button', { name: 'Get started' })).toBeInTheDocument()
  })

  it('forwards continue, back, and skip intents', async () => {
    const onContinue = vi.fn()
    const onBack = vi.fn()
    const onSkip = vi.fn()
    renderControls({ onContinue, onBack, onSkip })

    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    await userEvent.click(screen.getByRole('button', { name: 'Back' }))
    await userEvent.click(screen.getByRole('button', { name: 'Skip' }))

    expect(onContinue).toHaveBeenCalledTimes(1)
    expect(onBack).toHaveBeenCalledTimes(1)
    expect(onSkip).toHaveBeenCalledTimes(1)
  })

  it('shows the pending label on Skip (the completing control) on a non-final step', () => {
    renderControls({ isLastStep: false, isSubmitting: true, continueLabel: 'Continue' })

    expect(screen.getByRole('button', { name: 'Finishing\u2026' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled()
  })

  it('shows the pending label on the primary (the completing control) on the final step', () => {
    renderControls({ isLastStep: true, isSubmitting: true, continueLabel: 'Get started' })

    expect(screen.getByRole('button', { name: 'Finishing\u2026' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Skip' })).toBeDisabled()
  })

  it('surfaces an error as an inline alert', () => {
    renderControls({ error: 'Could not finish.' })

    expect(screen.getByRole('alert')).toHaveTextContent('Could not finish.')
  })
})
