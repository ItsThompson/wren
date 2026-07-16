import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { useLocation } from 'react-router'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { usePublicClient, useSessionClient } from '@/api'
import { useAuth } from '@/auth'

import { buildAuthUser, buildAuthValue } from './auth-harness'
import { createHookWrapper } from './createHookWrapper'

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('createHookWrapper', () => {
  it('renders a hook through the ApiClientProvider so useSessionClient resolves', () => {
    const { result } = renderHook(() => useSessionClient(), { wrapper: createHookWrapper() })

    expect(typeof result.current.GET).toBe('function')
  })

  it('also resolves the public client from the same provider', () => {
    const { result } = renderHook(() => usePublicClient(), { wrapper: createHookWrapper() })

    expect(typeof result.current.GET).toBe('function')
  })

  it('defaults to an anonymous controlled auth layer with no network', () => {
    const { result } = renderHook(() => useAuth(), { wrapper: createHookWrapper() })

    expect(result.current.status).toBe('anonymous')
    expect(result.current.user).toBeNull()
  })

  it('honors a controlled authValue', () => {
    const authValue = buildAuthValue({
      status: 'authenticated',
      user: buildAuthUser({ username: 'grace' }),
    })

    const { result } = renderHook(() => useAuth(), { wrapper: createHookWrapper({ authValue }) })

    expect(result.current.status).toBe('authenticated')
    expect(result.current.user?.username).toBe('grace')
  })

  it('starts the router at the provided initialEntries', () => {
    const { result } = renderHook(() => useLocation(), {
      wrapper: createHookWrapper({ initialEntries: ['/roadmaps/42'] }),
    })

    expect(result.current.pathname).toBe('/roadmaps/42')
  })

  it('mounts the real AuthProvider under useRealAuth and resolves resume via /auth/refresh', async () => {
    server.use(
      http.post('*/auth/refresh', () => HttpResponse.json(buildAuthUser({ username: 'ada' }))),
    )

    const { result } = renderHook(() => useAuth(), {
      wrapper: createHookWrapper({ useRealAuth: true }),
    })

    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    expect(result.current.user?.username).toBe('ada')
  })
})
