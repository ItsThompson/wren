import { describe, expect, it } from 'vitest'

import { swrRevalidationPosture } from './swr-config'

describe('swrRevalidationPosture', () => {
  it('pins the global SWR revalidation posture to the section 07 values', () => {
    // The single source of truth App.tsx and the test harness both bind. The
    // observable cross-route cache effect is asserted in the swr-posture
    // acceptance test; this locks the constant itself at the unit boundary.
    expect(swrRevalidationPosture).toEqual({
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      revalidateIfStale: false,
      revalidateOnMount: true,
      dedupingInterval: 2000,
    })
  })
})
