import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import type { AuthStatus, AuthUser } from '@/auth/types'
import { buildAuthUser, buildAuthValue, renderWithAuth } from '@/test/auth-harness'

import { OnboardingRouteGuard } from './OnboardingRouteGuard'

/**
 * Mount the guard at `/onboarding` alongside marker routes so each decision is
 * observable: the wizard child renders in place, or a `<Navigate>` swaps in the
 * `/auth` or `/dashboard` marker.
 */
function renderGuard(authValue: ReturnType<typeof buildAuthValue>) {
  return renderWithAuth(
    <Routes>
      <Route
        path="/onboarding"
        element={
          <OnboardingRouteGuard>
            <div>wizard</div>
          </OnboardingRouteGuard>
        }
      />
      <Route path="/auth" element={<div>auth screen</div>} />
      <Route path="/dashboard" element={<div>dashboard screen</div>} />
    </Routes>,
    { authValue, initialEntries: ['/onboarding'] },
  )
}

/** A user payload missing the flag entirely (the backend version-skew shape). */
function userWithoutFlag(): AuthUser {
  const user = buildAuthUser()
  delete (user as { has_completed_onboarding?: boolean }).has_completed_onboarding
  return user
}

function authValueFor(status: AuthStatus, user: AuthUser | null) {
  return buildAuthValue({ status, user })
}

describe('OnboardingRouteGuard', () => {
  it('renders the loading placeholder while the session resolves', () => {
    renderGuard(authValueFor('loading', null))

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument()
    expect(screen.queryByText('wizard')).not.toBeInTheDocument()
  })

  it('redirects an anonymous visitor to /auth', () => {
    renderGuard(authValueFor('anonymous', null))

    expect(screen.getByText('auth screen')).toBeInTheDocument()
    expect(screen.queryByText('wizard')).not.toBeInTheDocument()
  })

  it('renders the wizard for an authenticated, explicitly un-onboarded user', () => {
    renderGuard(authValueFor('authenticated', buildAuthUser({ has_completed_onboarding: false })))

    expect(screen.getByText('wizard')).toBeInTheDocument()
  })

  it('redirects an already-onboarded user to /dashboard', () => {
    renderGuard(authValueFor('authenticated', buildAuthUser({ has_completed_onboarding: true })))

    expect(screen.getByText('dashboard screen')).toBeInTheDocument()
    expect(screen.queryByText('wizard')).not.toBeInTheDocument()
  })

  it('fails open: redirects to /dashboard when the flag is missing/undefined', () => {
    renderGuard(authValueFor('authenticated', userWithoutFlag()))

    expect(screen.getByText('dashboard screen')).toBeInTheDocument()
    expect(screen.queryByText('wizard')).not.toBeInTheDocument()
  })
})
