import type { SWRConfiguration } from 'swr'

/**
 * The pinned global SWR revalidation posture (spec section 07). This is a
 * behavior-preservation choice, not a tuning exercise: today's hooks fetch once
 * on mount and never background-revalidate, so `revalidateIfStale:false` +
 * `revalidateOnMount:true` reproduces that exactly while enabling the new shared
 * cross-route cache reuse, and `dedupingInterval` coalesces co-mounted reads of
 * the same key into a single request.
 *
 * Owned here as the single source of truth so the app root (`App.tsx`) and the
 * test harness (`renderWithProviders`) bind identical values and cannot drift.
 */
export const swrRevalidationPosture = {
  revalidateOnFocus: false,
  revalidateOnReconnect: false,
  revalidateIfStale: false,
  revalidateOnMount: true,
  dedupingInterval: 2000,
} as const satisfies SWRConfiguration
