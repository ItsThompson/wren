import type { ReactElement } from 'react'
import { render, type RenderOptions, type RenderResult } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { SWRConfig } from 'swr'

import { ApiClientProvider, swrRevalidationPosture } from '@/api'
import { AuthProvider } from '@/auth'
import { AuthContext } from '@/auth/auth-context'
import type { AuthContextValue } from '@/auth/types'

import { buildAuthValue } from './auth-harness'

/** The API base every harness render binds to unless a test overrides it. */
export const TEST_API_BASE = 'https://api.test'

/**
 * The SWR posture for tests. `provider: () => new Map()` hands each render a
 * FRESH cache so SWR's module-level cache cannot leak between tests (the top
 * false-green risk, VC2). The revalidate/dedupe fields come from the SAME
 * {@link swrRevalidationPosture} constant the production `SWRConfig` binds at the
 * app root (section 07), so test behavior matches production and cannot drift.
 * The `provider` factory is invoked once per mounted `SWRConfig`, so sharing this
 * constant still yields a distinct `Map` per render.
 */
const SWR_TEST_CONFIG = {
  provider: () => new Map(),
  ...swrRevalidationPosture,
}

export interface ProviderRenderOptions extends Omit<RenderOptions, 'wrapper'> {
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
 * Render `ui` under a fresh SWR cache + the shared API clients + an auth layer +
 * a router, wired the same way production is, so cache does not leak across tests
 * and hooks resolve the same clients as the app.
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
export function renderWithProviders(
  ui: ReactElement,
  options: ProviderRenderOptions = {},
): RenderResult {
  const {
    baseUrl = TEST_API_BASE,
    initialEntries = ['/'],
    authValue,
    useRealAuth = false,
    ...rest
  } = options

  const routed = <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
  const withAuth = useRealAuth ? (
    <AuthProvider>{routed}</AuthProvider>
  ) : (
    <AuthContext.Provider value={authValue ?? buildAuthValue()}>{routed}</AuthContext.Provider>
  )

  return render(
    <SWRConfig value={SWR_TEST_CONFIG}>
      <ApiClientProvider baseUrl={baseUrl}>{withAuth}</ApiClientProvider>
    </SWRConfig>,
    rest,
  )
}
