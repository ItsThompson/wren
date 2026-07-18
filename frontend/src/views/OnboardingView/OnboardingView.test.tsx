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
  it('renders the Welcome step and the progress indicator', () => {
    renderOnboardingView()

    expect(screen.getByText('Welcome to Wren')).toBeInTheDocument()
    expect(screen.getByLabelText('Step 1 of 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
  })

  it('completes end to end: Continue applies the user and lands on /dashboard', async () => {
    const onboarded = buildAuthUser({ has_completed_onboarding: true })
    server.use(http.post(COMPLETE_URL, () => HttpResponse.json(onboarded)))
    const applyUser = buildAuthValue().applyUser
    renderOnboardingView(applyUser)

    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))

    expect(await screen.findByText('dashboard screen')).toBeInTheDocument()
    expect(applyUser).toHaveBeenCalledWith(onboarded)
  })

  it('skips end to end through the same terminal path', async () => {
    const onboarded = buildAuthUser({ has_completed_onboarding: true })
    server.use(http.post(COMPLETE_URL, () => HttpResponse.json(onboarded)))
    renderOnboardingView()

    await userEvent.click(screen.getByRole('button', { name: 'Skip' }))

    expect(await screen.findByText('dashboard screen')).toBeInTheDocument()
  })
})
