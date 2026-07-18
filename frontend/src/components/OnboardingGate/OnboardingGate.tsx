import { Navigate, Outlet } from 'react-router'

import { useAuth } from '@/auth'
import { RouteLoading } from '@/components/states'

/**
 * Guards the in-app authenticated routes: it keeps a signed-in, un-onboarded
 * user inside onboarding and lets everyone else through. Rendered as a layout
 * (parent) route, so it either renders `<Outlet/>` (the matched child view) or
 * redirects.
 *
 * Decisions (see §07 "Redirect decision rules"):
 * - `loading` → neutral full-screen loader (US-GUARD-05: never misroute or flash
 *   the guarded view while the session resolves)
 * - `anonymous` → pass through; the target view self-gates on auth (this guard is
 *   not the auth boundary)
 * - `authenticated` + flag explicitly `false` → redirect to `/onboarding`
 *   (US-GUARD-01); returned instead of `<Outlet/>`, so the guarded view never
 *   mounts and its data fetching never begins
 * - `authenticated` + flag `true` OR missing/`undefined` → render the route
 *
 * The missing/`undefined` case fails **open** (treated as onboarded): it only
 * arises in a backend/frontend version-skew window, where redirecting every user
 * to a wizard whose completion endpoint may be gone would trap them. Failing open
 * degrades safely (§08 rollback safety).
 *
 * The `/authorize` OAuth-consent exemption (US-GUARD-03) is **structural**: that
 * route is mounted outside this gate in the route tree, so the gate performs no
 * location check. `replace` avoids leaving the redirect in history.
 */
export function OnboardingGate() {
  const { status, user } = useAuth()

  if (status === 'loading') return <RouteLoading />
  if (status === 'anonymous') return <Outlet />
  if (user?.has_completed_onboarding === false) return <Navigate to="/onboarding" replace />
  return <Outlet />
}
