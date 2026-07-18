import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { OnboardingStepProps } from '../types'
import { HowItWorksStep } from './HowItWorksStep'

function buildProps(overrides: Partial<OnboardingStepProps> = {}): OnboardingStepProps {
  return {
    onContinue: vi.fn(),
    onBack: vi.fn(),
    onSkip: vi.fn(),
    isFirstStep: false,
    isLastStep: true,
    isSubmitting: false,
    error: null,
    ...overrides,
  }
}

describe('HowItWorksStep', () => {
  it('explains that agents author roadmaps and humans follow and track them', () => {
    render(<HowItWorksStep {...buildProps()} />)

    expect(screen.getByRole('heading', { name: /agents author, you follow/i })).toBeInTheDocument()
    expect(screen.getByText(/tracks your progress and suggests what to do/i)).toBeInTheDocument()
  })

  it('completes via its primary "Get started" action on the final step', async () => {
    const onContinue = vi.fn()
    render(<HowItWorksStep {...buildProps({ onContinue })} />)

    await userEvent.click(screen.getByRole('button', { name: 'Get started' }))

    expect(onContinue).toHaveBeenCalledTimes(1)
  })

  it('forwards back and skip intents', async () => {
    const onBack = vi.fn()
    const onSkip = vi.fn()
    render(<HowItWorksStep {...buildProps({ onBack, onSkip })} />)

    await userEvent.click(screen.getByRole('button', { name: 'Back' }))
    await userEvent.click(screen.getByRole('button', { name: 'Skip' }))

    expect(onBack).toHaveBeenCalledTimes(1)
    expect(onSkip).toHaveBeenCalledTimes(1)
  })
})
