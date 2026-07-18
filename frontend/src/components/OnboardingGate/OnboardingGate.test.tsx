import { useEffect } from 'react'
import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { AuthStatus, AuthUser } from '@/auth/types'
import { buildAuthUser, buildAuthValue, renderWithAuth } from '@/test/auth-harness'

import { OnboardingGate } from './OnboardingGate'

/**
 * A stand-in for a guarded view. It records a render-time "fetch" so tests can
 * prove the gate short-circuits BEFORE the guarded view mounts (its data
 * fetching never begins) on an un-onboarded redirect.
 */
function GuardedView({ onMount }: { onMount: () => void }) {
  useEffect(() => {
    onMount()
  }, [onMount])
  return <div>guarded content</div>
}

/**
 * Mount the gate as a layout route over a guarded child, alongside an
 * `/onboarding` marker so each decision is observable: the guarded child renders
 * in place, the loader swaps in, or a `<Navigate>` swaps in the onboarding
 * marker.
 */
function renderGate(
  authValue: ReturnType<typeof buildAuthValue>,
  onGuardedMount: () => void = vi.fn(),
) {
  return renderWithAuth(
    <Routes>
      <Route element={<OnboardingGate />}>
        <Route path="/dashboard" element={<GuardedView onMount={onGuardedMount} />} />
      </Route>
      <Route path="/onboarding" element={<div>onboarding wizard</div>} />
    </Routes>,
    { authValue, initialEntries: ['/dashboard'] },
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

describe('OnboardingGate', () => {
  it('renders the loading placeholder while the session resolves, without misrouting', () => {
    renderGate(authValueFor('loading', null))

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument()
    expect(screen.queryByText('guarded content')).not.toBeInTheDocument()
    expect(screen.queryByText('onboarding wizard')).not.toBeInTheDocument()
  })

  it('passes an anonymous visitor through to the guarded view, never to onboarding', () => {
    renderGate(authValueFor('anonymous', null))

    expect(screen.getByText('guarded content')).toBeInTheDocument()
    expect(screen.queryByText('onboarding wizard')).not.toBeInTheDocument()
  })

  it('redirects an authenticated, explicitly un-onboarded user to /onboarding', () => {
    renderGate(authValueFor('authenticated', buildAuthUser({ has_completed_onboarding: false })))

    expect(screen.getByText('onboarding wizard')).toBeInTheDocument()
    expect(screen.queryByText('guarded content')).not.toBeInTheDocument()
  })

  it('never mounts the guarded view (no data fetching) on an un-onboarded redirect', () => {
    const onGuardedMount = vi.fn()
    renderGate(
      authValueFor('authenticated', buildAuthUser({ has_completed_onboarding: false })),
      onGuardedMount,
    )

    expect(screen.getByText('onboarding wizard')).toBeInTheDocument()
    expect(onGuardedMount).not.toHaveBeenCalled()
  })

  it('renders the route for an onboarded user and never routes to onboarding', () => {
    renderGate(authValueFor('authenticated', buildAuthUser({ has_completed_onboarding: true })))

    expect(screen.getByText('guarded content')).toBeInTheDocument()
    expect(screen.queryByText('onboarding wizard')).not.toBeInTheDocument()
  })

  it('fails open: renders the route when the flag is missing/undefined', () => {
    renderGate(authValueFor('authenticated', userWithoutFlag()))

    expect(screen.getByText('guarded content')).toBeInTheDocument()
    expect(screen.queryByText('onboarding wizard')).not.toBeInTheDocument()
  })
})
