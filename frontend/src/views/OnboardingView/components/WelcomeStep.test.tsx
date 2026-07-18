import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { OnboardingStepProps } from '../types'
import { WelcomeStep } from './WelcomeStep'

function buildProps(overrides: Partial<OnboardingStepProps> = {}): OnboardingStepProps {
  return {
    onContinue: vi.fn(),
    onBack: vi.fn(),
    onSkip: vi.fn(),
    isFirstStep: true,
    isLastStep: false,
    isSubmitting: false,
    error: null,
    ...overrides,
  }
}

describe('WelcomeStep', () => {
  it('renders the welcome content with Continue and Skip but no Back on the first step', () => {
    render(<WelcomeStep {...buildProps()} />)

    expect(screen.getByText('Welcome to Wren')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Skip' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument()
  })

  it('forwards the continue and skip intents to its callbacks', async () => {
    const onContinue = vi.fn()
    const onSkip = vi.fn()
    render(<WelcomeStep {...buildProps({ onContinue, onSkip })} />)

    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    await userEvent.click(screen.getByRole('button', { name: 'Skip' }))

    expect(onContinue).toHaveBeenCalledTimes(1)
    expect(onSkip).toHaveBeenCalledTimes(1)
  })

  it('disables both controls and shows the pending label on Skip (the completing control) while submitting', () => {
    render(<WelcomeStep {...buildProps({ isSubmitting: true })} />)

    // Welcome is not the last step, so Skip is the control that completes.
    expect(screen.getByRole('button', { name: 'Finishing\u2026' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
  })

  it('surfaces a completion error as an inline alert', () => {
    render(<WelcomeStep {...buildProps({ error: 'Something went wrong.' })} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong.')
  })
})
