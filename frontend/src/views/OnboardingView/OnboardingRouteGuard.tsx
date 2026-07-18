import type { ReactNode } from 'react'
import { Navigate } from 'react-router'

import { useAuth } from '@/auth'
import { RouteLoading } from '@/components/states'

interface OnboardingRouteGuardProps {
  children: ReactNode
}

/**
 * Guards the `/onboarding` route itself: it keeps already-onboarded users out and
 * sends anonymous visitors to auth, so only a signed-in, un-onboarded user sees
 * the wizard.
 *
 * Decisions (see §07 "Redirect decision rules"):
 * - `loading` → neutral full-screen loader (no misroute while the session resolves)
 * - `anonymous` → redirect to `/auth` (cannot onboard without a session)
 * - `authenticated` + flag explicitly `false` → render the wizard
 * - `authenticated` + flag `true` OR missing/`undefined` → redirect to `/dashboard`
 *
 * The missing/`undefined` case fails **open** (treated as onboarded): it only
 * arises in a backend/frontend version-skew window, where trapping users in a
 * wizard whose completion endpoint may be gone would be worse than skipping
 * onboarding once. `replace` avoids leaving the redirect in history.
 */
export function OnboardingRouteGuard({ children }: OnboardingRouteGuardProps) {
  const { status, user } = useAuth()

  if (status === 'loading') return <RouteLoading />
  if (status === 'anonymous') return <Navigate to="/auth" replace />
  if (user?.has_completed_onboarding === false) return <>{children}</>
  return <Navigate to="/dashboard" replace />
}
