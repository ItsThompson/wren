import { act, renderHook, waitFor } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import type { AuthContextValue } from '@/auth/types'
import { buildAuthUser, buildAuthValue } from '@/test/auth-harness'
import { createHookWrapper } from '@/test/createHookWrapper'

import { useOnboarding } from './useOnboarding'

const BASE = 'https://api.test'
const COMPLETE_URL = `${BASE}/me/onboarding:complete`

// The hook resolves `navigate` from the router; a spy stands in so post-success
// navigation (and its ordering relative to `applyUser`) is assertable headlessly.
const { navigateSpy } = vi.hoisted(() => ({ navigateSpy: vi.fn() }))
vi.mock('react-router', async (importActual) => {
  const actual = await importActual<typeof import('react-router')>()
  return { ...actual, useNavigate: () => navigateSpy }
})

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  navigateSpy.mockReset()
})
afterAll(() => server.close())

/**
 * Render `useOnboarding` under the production-parity provider stack (fresh SWR
 * cache + shared clients + a controlled auth context + router). The returned
 * `authValue` carries the stubbed `applyUser` so tests can assert it and its
 * ordering relative to the navigate spy.
 */
function renderOnboarding(overrides: Partial<AuthContextValue> = {}) {
  const authValue = buildAuthValue({
    status: 'authenticated',
    user: buildAuthUser({ has_completed_onboarding: false }),
    ...overrides,
  })
  const view = renderHook(() => useOnboarding(), {
    wrapper: createHookWrapper({ baseUrl: BASE, authValue }),
  })
  return { ...view, authValue }
}

describe('useOnboarding step machine', () => {
  it('opens on the first (Welcome) step, which is also the last in this slice', () => {
    const { result } = renderOnboarding()

    expect(result.current.state.stepIndex).toBe(0)
    expect(result.current.state.stepCount).toBe(1)
    expect(result.current.state.isFirstStep).toBe(true)
    expect(result.current.state.isLastStep).toBe(true)
    expect(result.current.state.phase).toBe('idle')
    expect(result.current.state.error).toBeNull()
  })

  it('clamps next and back to the step bounds', () => {
    const { result } = renderOnboarding()

    act(() => result.current.actions.next())
    expect(result.current.state.stepIndex).toBe(0) // clamped at the last step

    act(() => result.current.actions.back())
    expect(result.current.state.stepIndex).toBe(0) // clamped at the first step
  })
})

describe('useOnboarding completion', () => {
  it('applies the returned user BEFORE navigating to /dashboard (replace)', async () => {
    const onboarded = buildAuthUser({ has_completed_onboarding: true })
    server.use(http.post(COMPLETE_URL, () => HttpResponse.json(onboarded)))
    const { result, authValue } = renderOnboarding()

    act(() => result.current.actions.submit())

    await waitFor(() =>
      expect(navigateSpy).toHaveBeenCalledWith('/dashboard', { replace: true }),
    )
    expect(authValue.applyUser).toHaveBeenCalledWith(onboarded)
    // The invariant that prevents the guard redirect loop: applyUser first.
    expect(vi.mocked(authValue.applyUser).mock.invocationCallOrder[0]).toBeLessThan(
      navigateSpy.mock.invocationCallOrder[0],
    )
  })

  it('drives the same completion path when skipping', async () => {
    const onboarded = buildAuthUser({ has_completed_onboarding: true })
    server.use(http.post(COMPLETE_URL, () => HttpResponse.json(onboarded)))
    const { result, authValue } = renderOnboarding()

    act(() => result.current.actions.skip())

    await waitFor(() =>
      expect(navigateSpy).toHaveBeenCalledWith('/dashboard', { replace: true }),
    )
    expect(authValue.applyUser).toHaveBeenCalledWith(onboarded)
  })

  it('enters the submitting phase while the completion call is in flight', async () => {
    const onboarded = buildAuthUser({ has_completed_onboarding: true })
    server.use(
      http.post(COMPLETE_URL, async () => {
        await delay()
        return HttpResponse.json(onboarded)
      }),
    )
    const { result } = renderOnboarding()

    act(() => result.current.actions.submit())
    expect(result.current.state.phase).toBe('submitting')

    await waitFor(() => expect(navigateSpy).toHaveBeenCalled())
  })

  it('on failure stays on the step, surfaces an inline error, and does not apply/navigate', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    server.use(http.post(COMPLETE_URL, () => new HttpResponse(null, { status: 500 })))
    const { result, authValue } = renderOnboarding()

    act(() => result.current.actions.submit())

    await waitFor(() => expect(result.current.state.phase).toBe('error'))
    expect(result.current.state.error).toBe("Couldn't finish setup. Please try again.")
    expect(result.current.state.stepIndex).toBe(0)
    expect(authValue.applyUser).not.toHaveBeenCalled()
    expect(navigateSpy).not.toHaveBeenCalled()
    expect(errorSpy).toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('treats a network-level failure as a completion error', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    server.use(http.post(COMPLETE_URL, () => HttpResponse.error()))
    const { result, authValue } = renderOnboarding()

    act(() => result.current.actions.submit())

    await waitFor(() => expect(result.current.state.phase).toBe('error'))
    expect(result.current.state.error).toBe("Couldn't finish setup. Please try again.")
    expect(authValue.applyUser).not.toHaveBeenCalled()
    expect(navigateSpy).not.toHaveBeenCalled()
    expect(errorSpy).toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('recovers to idle-submitting on retry after a failure', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const onboarded = buildAuthUser({ has_completed_onboarding: true })
    server.use(http.post(COMPLETE_URL, () => new HttpResponse(null, { status: 500 })))
    const { result, authValue } = renderOnboarding()

    act(() => result.current.actions.submit())
    await waitFor(() => expect(result.current.state.phase).toBe('error'))

    // Second attempt succeeds; the error clears and the terminal path runs.
    server.use(http.post(COMPLETE_URL, () => HttpResponse.json(onboarded)))
    act(() => result.current.actions.submit())

    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/dashboard', { replace: true }))
    expect(authValue.applyUser).toHaveBeenCalledWith(onboarded)
    errorSpy.mockRestore()
  })
})
