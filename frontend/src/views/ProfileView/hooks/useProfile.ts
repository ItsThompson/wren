import { keys, usePublicApiQuery } from '@/api'
import type { Problem } from '@/lib/problem'

import type { ProfileData, ProfileState } from '../types'

/**
 * Derive the view's semantic phase-state from the SWR read result. A 404 is the
 * first-class `notfound` state; every other failure (including a network
 * failure, where `Problem.status` is `null`) is the generic `error`. The loading
 * guard holds only while there is no cached `data`, so a background revalidation
 * keeps the last-loaded profile on screen instead of flashing the skeleton.
 */
function toProfileState(
  data: ProfileData | undefined,
  error: Problem | undefined,
  isLoading: boolean,
): ProfileState {
  if (isLoading && !data) return { phase: 'loading' }
  if (error?.status === 404) return { phase: 'notfound' }
  if (error) return { phase: 'error' }
  if (data) return { phase: 'loaded', profile: data }
  return { phase: 'loading' }
}

/**
 * Owns the public profile fetch (`GET /users/{handle}`): a handle's
 * published-public roadmaps. Reads through {@link usePublicApiQuery} so it binds
 * the shared public (credential-free) client from context: the profile is public
 * and viewer-agnostic, so no session is sent or needed and the backend never
 * exposes drafts, private roadmaps, or who follows what.
 *
 * SWR owns fetching, de-duplication, and in-flight cancellation; this hook is
 * just the pure result→phase-state mapping plus a `reload` that revalidates the
 * cache entry via `mutate()`.
 */
export function useProfile(handle: string): {
  state: ProfileState
  reload: () => void
} {
  const { data, error, isLoading, mutate } = usePublicApiQuery(keys.profile(handle), (client) =>
    client.GET('/users/{handle}', { params: { path: { handle } } }),
  )

  return {
    state: toProfileState(data, error, isLoading),
    reload: () => {
      void mutate()
    },
  }
}
