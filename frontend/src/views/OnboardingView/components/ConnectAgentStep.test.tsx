import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { ConnectAgentStepProps } from '../types'
import { ConnectAgentStep } from './ConnectAgentStep'

function buildProps(overrides: Partial<ConnectAgentStepProps> = {}): ConnectAgentStepProps {
  return {
    onContinue: vi.fn(),
    onBack: vi.fn(),
    onSkip: vi.fn(),
    isFirstStep: false,
    isLastStep: false,
    isSubmitting: false,
    error: null,
    mcpUrl: 'https://mcp.usewren.com/mcp',
    connectionsHref: '/settings/connections',
    docsHref: 'https://docs.usewren.com/getting-started',
    ...overrides,
  }
}

function renderStep(overrides: Partial<ConnectAgentStepProps> = {}) {
  return render(
    <MemoryRouter>
      <ConnectAgentStep {...buildProps(overrides)} />
    </MemoryRouter>,
  )
}

describe('ConnectAgentStep', () => {
  it('displays the MCP URL from its prop', () => {
    renderStep({ mcpUrl: 'https://mcp.example.test/mcp' })

    expect(screen.getByText('https://mcp.example.test/mcp')).toBeInTheDocument()
  })

  it('explains the OAuth consent and that authorized agents appear on Connected agents', () => {
    renderStep()

    expect(screen.getByText(/OAuth consent screen/i)).toBeInTheDocument()
    expect(screen.getByText(/no API keys/i)).toBeInTheDocument()
  })

  it('links to the connections surface and the docs Getting Started guide', () => {
    renderStep({
      connectionsHref: '/settings/connections',
      docsHref: 'https://docs.usewren.com/getting-started',
    })

    expect(screen.getByRole('link', { name: 'Connected agents' })).toHaveAttribute(
      'href',
      '/settings/connections',
    )
    const docsLink = screen.getByRole('link', { name: 'Getting Started guide' })
    expect(docsLink).toHaveAttribute('href', 'https://docs.usewren.com/getting-started')
    expect(docsLink).toHaveAttribute('target', '_blank')
    expect(docsLink).toHaveAttribute('rel', 'noreferrer')
  })

  it('forwards continue, back, and skip intents (nothing is required to advance)', async () => {
    const onContinue = vi.fn()
    const onBack = vi.fn()
    const onSkip = vi.fn()
    renderStep({ onContinue, onBack, onSkip })

    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    await userEvent.click(screen.getByRole('button', { name: 'Back' }))
    await userEvent.click(screen.getByRole('button', { name: 'Skip' }))

    expect(onContinue).toHaveBeenCalledTimes(1)
    expect(onBack).toHaveBeenCalledTimes(1)
    expect(onSkip).toHaveBeenCalledTimes(1)
  })
})
