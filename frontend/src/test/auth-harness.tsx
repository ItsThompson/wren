import type { ReactElement } from 'react'
import { render, type RenderOptions, type RenderResult } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'

import { AuthContext } from '@/auth/auth-context'
import type { AuthContextValue, AuthUser } from '@/auth/types'

/** A valid authenticated-user fixture; override any field per test. */
export function buildAuthUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    username: 'ada',
    email: 'ada@example.com',
    created_at: '2026-07-15T00:00:00Z',
    has_completed_onboarding: true,
    ...overrides,
  }
}

/** A controllable auth context value with stubbed actions for component tests. */
export function buildAuthValue(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    status: 'anonymous',
    user: null,
    register: vi.fn(async () => ({ ok: true }) as const),
    login: vi.fn(async () => ({ ok: true }) as const),
    logout: vi.fn(async () => {}),
    ...overrides,
  }
}

interface AuthRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  authValue?: AuthContextValue
  initialEntries?: string[]
}

/**
 * Render a component under a fixed auth context + router, so component behavior
 * is tested against controlled session state without touching the network.
 */
export function renderWithAuth(ui: ReactElement, options: AuthRenderOptions = {}): RenderResult {
  const { authValue = buildAuthValue(), initialEntries = ['/'], ...rest } = options
  return render(
    <AuthContext.Provider value={authValue}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </AuthContext.Provider>,
    rest,
  )
}
