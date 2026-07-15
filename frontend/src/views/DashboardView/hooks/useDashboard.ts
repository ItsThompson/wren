import { keys, useApiQuery } from '@/api'
import type { Problem } from '@/lib/problem'

import type { DashboardData, DashboardState } from '../types'

/**
 * Derive the view's semantic phase-state from the SWR read result. Any failure
 * (including a network failure, where `Problem.status` is `null`) is the generic
 * `error`: the dashboard has no first-class per-status branch. The loading guard
 * holds only while there is no cached `data`, so a background revalidation keeps
 * the last-loaded dashboard on screen instead of flashing the skeleton.
 */
function toDashboardState(
  data: DashboardData | undefined,
  error: Problem | undefined,
  isLoading: boolean,
): DashboardState {
  if (isLoading && !data) return { phase: 'loading' }
  if (error) return { phase: 'error' }
  if (data) return { phase: 'loaded', authored: data.authored ?? [], followed: data.followed ?? [] }
  return { phase: 'loading' }
}

/**
 * Owns the private dashboard fetch (`GET /me/dashboard`): the caller's authored
 * roadmaps (any status) plus the ones they follow. Reads through
 * {@link useApiQuery} so it binds the shared session client (credentials +
 * transparent refresh) from context; the backend scopes the response to the
 * resolved session user, so another user's dashboard is never returned.
 *
 * Fetching is gated on `enabled` via a null key: the caller enables it only once
 * the session resolves to authenticated, and a `null` key never fetches (no
 * request, no loading churn), so the view's anonymous branch (driven by
 * `useAuth().status`) is left to render the login prompt. `reload` revalidates
 * the cache entry via `mutate()` for the inline error-retry.
 */
export function useDashboard(enabled: boolean): {
  state: DashboardState
  reload: () => void
} {
  const { data, error, isLoading, mutate } = useApiQuery(enabled ? keys.dashboard() : null, (client) =>
    client.GET('/me/dashboard'),
  )

  return {
    state: toDashboardState(data, error, isLoading),
    reload: () => {
      void mutate()
    },
  }
}
