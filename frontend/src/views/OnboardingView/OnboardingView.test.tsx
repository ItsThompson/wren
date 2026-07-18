import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { Route, Routes } from 'react-router'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { buildAuthUser, buildAuthValue } from '@/test/auth-harness'
import { renderWithProviders } from '@/test/renderWithProviders'

import { OnboardingView } from './OnboardingView'

const BASE = 'https://api.test'
const COMPLETE_URL = `${BASE}/me/onboarding:complete`

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

/** Mount the view at `/onboarding` with a `/dashboard` marker to observe the redirect. */
function renderOnboardingView(applyUser = buildAuthValue().applyUser) {
  const authValue = buildAuthValue({
    status: 'authenticated',
    user: buildAuthUser({ has_completed_onboarding: false }),
    applyUser,
  })
  return renderWithProviders(
    <Routes>
      <Route path="/onboarding" element={<OnboardingView />} />
      <Route path="/dashboard" element={<div>dashboard screen</div>} />
    </Routes>,
    { baseUrl: BASE, initialEntries: ['/onboarding'], authValue },
  )
}

describe('OnboardingView', () => {
  it('renders the Welcome step and the progress indicator on entry', () => {
    renderOnboardingView()

    expect(screen.getByText('Welcome to Wren')).toBeInTheDocument()
    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument()
  })

  it('advances forward through the steps, routing by id and updating progress', async () => {
    renderOnboardingView()

    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByText('Step 2 of 3')).toBeInTheDocument()
    expect(screen.getByText('Connect an agent')).toBeInTheDocument()
    // The MCP URL is sourced once at the view root and shown on the connect step.
    expect(screen.getByText('https://mcp.usewren.com/mcp')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByText('Step 3 of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Get started' })).toBeInTheDocument()
  })

  it('goes back to the previous step, returning from step 2 to Welcome', async () => {
    renderOnboardingView()

    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByText('Step 2 of 3')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument()
    expect(screen.getByText('Welcome to Wren')).toBeInTheDocument()
  })

  it('completes from the final step: Get started applies the user and lands on /dashboard', async () => {
    const onboarded = buildAuthUser({ has_completed_onboarding: true })
    server.use(http.post(COMPLETE_URL, () => HttpResponse.json(onboarded)))
    const applyUser = buildAuthValue().applyUser
    renderOnboardingView(applyUser)

    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    await userEvent.click(screen.getByRole('button', { name: 'Get started' }))

    expect(await screen.findByText('dashboard screen')).toBeInTheDocument()
    expect(applyUser).toHaveBeenCalledWith(onboarded)
  })

  it('skips from an intermediate step through the same terminal completion path', async () => {
    const onboarded = buildAuthUser({ has_completed_onboarding: true })
    server.use(http.post(COMPLETE_URL, () => HttpResponse.json(onboarded)))
    renderOnboardingView()

    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByText('Step 2 of 3')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Skip' }))

    expect(await screen.findByText('dashboard screen')).toBeInTheDocument()
  })
})
