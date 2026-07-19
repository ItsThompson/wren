import { screen } from '@testing-library/react'
import { http, HttpResponse, delay } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { keys, usePublicApiQuery } from '@/api'
import { useAuth } from '@/auth'

import { buildAuthUser, buildAuthValue } from './auth-harness'
import { renderWithProviders } from './renderWithProviders'

/**
 * A public read probe: renders the profile `display_name` for a handle through
 * the real `usePublicApiQuery` + `keys` + `runQuery` stack. Used to prove cache
 * isolation without migrating any view hook.
 */
function ProfileProbe({ handle }: { handle: string }) {
  const { data, error, isLoading } = usePublicApiQuery(keys.profile(handle), (client) =>
    client.GET('/users/{handle}', { params: { path: { handle } } }),
  )
  if (isLoading) return <p>loading</p>
  if (error) return <p role="alert">error {error.status}</p>
  return <p>{data?.display_name}</p>
}

/** Renders the resolved auth status + username so each auth mode is observable. */
function AuthProbe() {
  const { status, user } = useAuth()
  return (
    <p>
      status: {status}
      {user ? ` user: ${user.username}` : ''}
    </p>
  )
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// Deliberately module-scoped and NOT reset between the two tests: the point
// is to observe whether the second render fires its own network request or is
// served from a leaked module-level SWR cache.
let profileFetches = 0

const profileHandler = (displayName: string) =>
  http.get('*/users/:handle', async () => {
    profileFetches += 1
    await delay(20)
    return HttpResponse.json({ handle: 'ada', display_name: displayName, roadmaps: [] })
  })

describe('renderWithProviders cache isolation (VC2)', () => {
  it('populates a key from the network on the first render', async () => {
    server.use(profileHandler('Ada First'))

    renderWithProviders(<ProfileProbe handle="ada" />)

    expect(screen.getByText('loading')).toBeInTheDocument()
    expect(await screen.findByText('Ada First')).toBeInTheDocument()
    expect(profileFetches).toBe(1)
  })

  it('does not serve the previous test cached value for the same key', async () => {
    server.use(profileHandler('Ada Second'))

    renderWithProviders(<ProfileProbe handle="ada" />)

    // A fresh Map per render means the same key starts empty: the initial render
    // shows 'loading', never the prior test's cached 'Ada First'. A leaked
    // module-level cache would synchronously paint 'Ada First' on this mount.
    expect(screen.queryByText('Ada First')).not.toBeInTheDocument()
    expect(screen.getByText('loading')).toBeInTheDocument()

    // The second render then resolves its own payload via its own request.
    expect(await screen.findByText('Ada Second')).toBeInTheDocument()
    expect(profileFetches).toBe(2)
  })
})

describe('renderWithProviders auth modes', () => {
  const authedRefresh = (username: string) =>
    http.post('*/auth/refresh', () => HttpResponse.json(buildAuthUser({ username })))
  const anonRefresh = () => http.post('*/auth/refresh', () => new HttpResponse(null, { status: 401 }))

  it('useRealAuth mounts the real AuthProvider inside ApiClientProvider and resolves resume', async () => {
    server.use(authedRefresh('ada'))

    renderWithProviders(<AuthProbe />, { useRealAuth: true })

    // Reaching 'authenticated' proves the real AuthProvider resolved
    // useSessionClient() from the enclosing ApiClientProvider and drove resume
    // via the mocked POST /auth/refresh.
    expect(await screen.findByText('status: authenticated user: ada')).toBeInTheDocument()
  })

  it('useRealAuth resolves anonymous when refresh returns 401', async () => {
    server.use(anonRefresh())

    renderWithProviders(<AuthProbe />, { useRealAuth: true })

    expect(await screen.findByText('status: anonymous')).toBeInTheDocument()
  })

  it('authValue mounts a controlled AuthContext.Provider with no network', () => {
    renderWithProviders(<AuthProbe />, {
      authValue: buildAuthValue({ status: 'authenticated', user: buildAuthUser({ username: 'grace' }) }),
    })

    // Rendered synchronously from the controlled value; onUnhandledRequest:'error'
    // guarantees no /auth/refresh fired.
    expect(screen.getByText('status: authenticated user: grace')).toBeInTheDocument()
  })

  it('useRealAuth wins when both useRealAuth and authValue are passed', async () => {
    server.use(authedRefresh('real-ada'))

    renderWithProviders(<AuthProbe />, {
      useRealAuth: true,
      authValue: buildAuthValue({ status: 'authenticated', user: buildAuthUser({ username: 'controlled-grace' }) }),
    })

    expect(await screen.findByText('status: authenticated user: real-ada')).toBeInTheDocument()
    expect(screen.queryByText(/controlled-grace/)).not.toBeInTheDocument()
  })

  it('defaults to an anonymous controlled value when no auth mode is given', () => {
    renderWithProviders(<AuthProbe />)

    expect(screen.getByText('status: anonymous')).toBeInTheDocument()
  })
})
