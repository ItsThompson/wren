import type { ReactElement, ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { SWRConfig } from 'swr'

import { ApiClientProvider, swrRevalidationPosture } from '@/api'
import { AuthProvider } from '@/auth'
import { AuthContext } from '@/auth/auth-context'
import type { AuthContextValue } from '@/auth/types'

import { buildAuthValue } from './auth-harness'
import { TEST_API_BASE } from './test-api-base'

/**
 * The SWR posture for tests. `provider: () => new Map()` hands each mounted
 * `SWRConfig` a FRESH cache so SWR's module-level cache cannot leak between tests
 * (the top false-green risk, VC2). The revalidate/dedupe fields come from the
 * SAME {@link swrRevalidationPosture} constant the production `SWRConfig` binds at
 * the app root, so test behavior matches production and cannot drift. The
 * `provider` factory is invoked once per mounted `SWRConfig`, so sharing this
 * object still yields a distinct `Map` per render.
 */
const swrTestConfig = {
  provider: () => new Map(),
  ...swrRevalidationPosture,
}

export interface HookWrapperOptions {
  /** API base the shared clients bind to; defaults to {@link TEST_API_BASE}. */
  baseUrl?: string
  /** MemoryRouter start route(s); defaults to `['/']`. */
  initialEntries?: string[]
  /** Controlled auth context value (mutually exclusive with `useRealAuth`). */
  authValue?: AuthContextValue
  /**
   * Mount the real `<AuthProvider>` (which consumes the shared session client)
   * so a mocked `POST /auth/refresh` drives `resume()` and the `enabled` gate.
   * Wins over `authValue` when both are passed.
   */
  useRealAuth?: boolean
}

/**
 * Build the wrapper component that mounts a hook or component under the same
 * provider stack production uses, so hooks resolve the same clients as the app
 * and SWR cache cannot leak across tests. Returns a component suitable for both
 * `renderHook`'s and `render`'s `{ wrapper }` option.
 *
 * Composition: `SWRConfig` (fresh Map + pinned posture) → `ApiClientProvider`
 * (owns `baseUrl`) → auth layer → `MemoryRouter`. `AuthProvider` nests INSIDE
 * `ApiClientProvider` so `useSessionClient()` resolves.
 *
 * Auth resolution:
 * - `useRealAuth: true` → real `<AuthProvider>` (resume via mocked `/auth/refresh`)
 * - `authValue` provided → `<AuthContext.Provider value={authValue}>` (controlled)
 * - neither → a default anonymous controlled value (`buildAuthValue()`)
 */
export function createHookWrapper(
  options: HookWrapperOptions = {},
): ({ children }: { children: ReactNode }) => ReactElement {
  const { baseUrl = TEST_API_BASE, initialEntries = ['/'], authValue, useRealAuth = false } = options

  return function HookWrapper({ children }: { children: ReactNode }): ReactElement {
    const routed = <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
    const withAuth = useRealAuth ? (
      <AuthProvider>{routed}</AuthProvider>
    ) : (
      <AuthContext.Provider value={authValue ?? buildAuthValue()}>{routed}</AuthContext.Provider>
    )

    return (
      <SWRConfig value={swrTestConfig}>
        <ApiClientProvider baseUrl={baseUrl}>{withAuth}</ApiClientProvider>
      </SWRConfig>
    )
  }
}
