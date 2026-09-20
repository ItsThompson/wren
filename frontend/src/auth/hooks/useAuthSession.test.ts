import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { createSessionClient } from '@/auth/createSessionClient'
import { mockAuthUser } from '@/mocks/data'

import type { AuthResult } from '../types'
import { useAuthSession } from './useAuthSession'

const BASE = 'https://api.test'

const server = setupServer(
  http.get('*/auth/session', () => new HttpResponse(null, { status: 401 })),
  http.post('*/auth/refresh', () => new HttpResponse(null, { status: 401 })),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

/** An RFC 9457 problem+json response body. */
function problem(status: number, body: Record<string, unknown>) {
  return HttpResponse.json(
    { type: 'https://usewren.com/errors/x', status, ...body },
    { status, headers: { 'content-type': 'application/problem+json' } },
  )
}

/** The mount `resume()` probe with no session to resume: resolves to anonymous. */
function anonymousResume() {
  return http.post('*/auth/refresh', () => new HttpResponse(null, { status: 401 }))
}

/**
 * Render `useAuthSession` with a real session client and no providers: the hook
 * takes its client as a param, so MSW alone stands in for the network.
 */
function renderSession() {
  const client = createSessionClient(BASE)
  return renderHook(() => useAuthSession(client))
}

describe('useAuthSession bootstrap', () => {
  it('resolves to authenticated from a valid access session without refreshing', async () => {
    let refreshCalls = 0
    server.use(
      http.get('*/auth/session', () => HttpResponse.json(mockAuthUser)),
      http.post('*/auth/refresh', () => {
        refreshCalls += 1
        return HttpResponse.json(mockAuthUser)
      }),
    )
    const { result } = renderSession()

    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    expect(result.current.user).toEqual(mockAuthUser)
    expect(refreshCalls).toBe(0)
  })

  it('refreshes an expired access session before resolving authenticated', async () => {
    let refreshCalls = 0
    server.use(
      http.get('*/auth/session', () => new HttpResponse(null, { status: 401 })),
      http.post('*/auth/refresh', () => {
        refreshCalls += 1
        return HttpResponse.json(mockAuthUser)
      }),
    )
    const { result } = renderSession()

    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    expect(result.current.user).toEqual(mockAuthUser)
    expect(refreshCalls).toBe(1)
  })

  it('does not let a delayed bootstrap overwrite a successful login', async () => {
    let releaseSessionProbe!: () => void
    let refreshCalls = 0
    let sessionProbeReleased = false
    const sessionProbe = new Promise<void>((resolve) => {
      releaseSessionProbe = () => {
        sessionProbeReleased = true
        resolve()
      }
    })
    server.use(
      http.get('*/auth/session', async () => {
        await sessionProbe
        return new HttpResponse(null, { status: 401 })
      }),
      http.post('*/auth/login', () => HttpResponse.json(mockAuthUser)),
      http.post('*/auth/refresh', () => {
        refreshCalls += 1
        return new HttpResponse(null, { status: 401 })
      }),
    )
    const { result } = renderSession()

    await act(async () => {
      const outcome = await result.current.login({ email: 'ada@example.com', password: 'Str0ngPass' })
      expect(outcome).toEqual({ ok: true })
    })
    expect(result.current.status).toBe('authenticated')

    await act(async () => {
      releaseSessionProbe()
      await waitFor(() => expect(sessionProbeReleased).toBe(true))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })

    expect(result.current.status).toBe('authenticated')
    expect(result.current.user).toEqual(mockAuthUser)
    expect(refreshCalls).toBe(0)
  })

  it('serializes login behind an in-flight bootstrap refresh', async () => {
    const loginUser = { ...mockAuthUser, username: 'logged-in-user' }
    let releaseRefresh!: () => void
    let resolveRefreshStarted!: () => void
    let loginCalls = 0
    const refreshGate = new Promise<void>((resolve) => {
      releaseRefresh = resolve
    })
    const refreshStarted = new Promise<void>((resolve) => {
      resolveRefreshStarted = resolve
    })
    server.use(
      http.get('*/auth/session', () => new HttpResponse(null, { status: 401 })),
      http.post('*/auth/refresh', async () => {
        resolveRefreshStarted()
        await refreshGate
        return HttpResponse.json(mockAuthUser)
      }),
      http.post('*/auth/login', () => {
        loginCalls += 1
        return HttpResponse.json(loginUser)
      }),
    )
    const { result } = renderSession()
    await refreshStarted

    await act(async () => {
      const login = result.current.login({ email: 'ada@example.com', password: 'Str0ngPass' })
      await new Promise((resolve) => setTimeout(resolve, 0))
      expect(loginCalls).toBe(0)
      releaseRefresh()
      expect(await login).toEqual({ ok: true })
    })

    expect(loginCalls).toBe(1)
    expect(result.current.status).toBe('authenticated')
    expect(result.current.user).toEqual(loginUser)
  })

  it('resolves to anonymous when no session can be resumed (401)', async () => {
    server.use(anonymousResume())
    const { result } = renderSession()

    await waitFor(() => expect(result.current.status).toBe('anonymous'))
    expect(result.current.user).toBeNull()
  })

  it('resolves to anonymous when the refresh throws at the network level', async () => {
    server.use(http.post('*/auth/refresh', () => HttpResponse.error()))
    const { result } = renderSession()

    await waitFor(() => expect(result.current.status).toBe('anonymous'))
    expect(result.current.user).toBeNull()
  })
})

describe('useAuthSession login', () => {
  it('authenticates and returns ok on a successful login', async () => {
    server.use(anonymousResume(), http.post('*/auth/login', () => HttpResponse.json(mockAuthUser)))
    const { result } = renderSession()
    await waitFor(() => expect(result.current.status).toBe('anonymous'))

    let outcome: AuthResult | undefined
    await act(async () => {
      outcome = await result.current.login({ email: 'ada@example.com', password: 'Str0ngPass' })
    })

    expect(outcome).toEqual({ ok: true })
    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    expect(result.current.user).toEqual(mockAuthUser)
  })

  it('returns the problem message and stays anonymous on bad credentials', async () => {
    server.use(
      anonymousResume(),
      http.post('*/auth/login', () =>
        problem(401, { code: 'UNAUTHORIZED', detail: 'Invalid email or password.' }),
      ),
    )
    const { result } = renderSession()
    await waitFor(() => expect(result.current.status).toBe('anonymous'))

    let outcome: AuthResult | undefined
    await act(async () => {
      outcome = await result.current.login({ email: 'ada@example.com', password: 'nope' })
    })

    expect(outcome).toEqual({ ok: false, message: 'Invalid email or password.' })
    expect(result.current.status).toBe('anonymous')
    expect(result.current.user).toBeNull()
  })
})

describe('useAuthSession register', () => {
  it('authenticates and returns ok on a successful register', async () => {
    server.use(
      anonymousResume(),
      http.post('*/auth/register', () => HttpResponse.json(mockAuthUser, { status: 201 })),
    )
    const { result } = renderSession()
    await waitFor(() => expect(result.current.status).toBe('anonymous'))

    let outcome: AuthResult | undefined
    await act(async () => {
      outcome = await result.current.register({
        username: 'ada',
        email: 'ada@example.com',
        password: 'Str0ngPass',
      })
    })

    expect(outcome).toEqual({ ok: true })
    await waitFor(() => expect(result.current.status).toBe('authenticated'))
    expect(result.current.user).toEqual(mockAuthUser)
  })

  it('surfaces field-level errors on a register conflict', async () => {
    server.use(
      anonymousResume(),
      http.post('*/auth/register', () =>
        problem(409, {
          code: 'CONFLICT',
          detail: 'An account with this email already exists.',
          fields: { email: 'This email is already registered.' },
        }),
      ),
    )
    const { result } = renderSession()
    await waitFor(() => expect(result.current.status).toBe('anonymous'))

    let outcome: AuthResult | undefined
    await act(async () => {
      outcome = await result.current.register({
        username: 'ada',
        email: 'ada@example.com',
        password: 'Str0ngPass',
      })
    })

    expect(outcome).toEqual({
      ok: false,
      message: 'An account with this email already exists.',
      fields: { email: 'This email is already registered.' },
    })
    // A failed register must not authenticate.
    expect(result.current.status).toBe('anonymous')
  })
})

describe('useAuthSession applyUser', () => {
  it('replaces the current user and marks the session authenticated', async () => {
    server.use(anonymousResume())
    const { result } = renderSession()
    await waitFor(() => expect(result.current.status).toBe('anonymous'))

    const onboarded = { ...mockAuthUser, has_completed_onboarding: true }
    act(() => {
      result.current.applyUser(onboarded)
    })

    expect(result.current.status).toBe('authenticated')
    expect(result.current.user).toEqual(onboarded)
  })
})

describe('useAuthSession logout', () => {
  it('clears the session on a successful logout', async () => {
    server.use(
      http.post('*/auth/refresh', () => HttpResponse.json(mockAuthUser)),
      http.post('*/auth/logout', () => new HttpResponse(null, { status: 204 })),
    )
    const { result } = renderSession()
    await waitFor(() => expect(result.current.status).toBe('authenticated'))

    await act(async () => {
      await result.current.logout()
    })

    expect(result.current.status).toBe('anonymous')
    expect(result.current.user).toBeNull()
  })

  it('clears the local session even when the logout request rejects', async () => {
    server.use(
      http.post('*/auth/refresh', () => HttpResponse.json(mockAuthUser)),
      http.post('*/auth/logout', () => HttpResponse.error()),
    )
    const { result } = renderSession()
    await waitFor(() => expect(result.current.status).toBe('authenticated'))

    await act(async () => {
      await result.current.logout()
    })

    // A rejected logout POST must still drop the client to anonymous.
    expect(result.current.status).toBe('anonymous')
    expect(result.current.user).toBeNull()
  })
})
