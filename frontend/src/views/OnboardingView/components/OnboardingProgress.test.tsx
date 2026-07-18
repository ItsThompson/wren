import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { OnboardingProgress } from './OnboardingProgress'

describe('OnboardingProgress', () => {
  it('labels the current position from the index and total it is given', () => {
    render(<OnboardingProgress stepIndex={0} stepCount={1} />)

    expect(screen.getByLabelText('Step 1 of 1')).toBeInTheDocument()
    expect(screen.getByText('Step 1 of 1')).toBeInTheDocument()
  })

  it('reflects a later position without tracking it independently', () => {
    render(<OnboardingProgress stepIndex={1} stepCount={3} />)

    expect(screen.getByLabelText('Step 2 of 3')).toBeInTheDocument()
  })
})
