import { isValidElement } from 'react'
import { render, screen } from '@testing-library/react'
import type { RouteObject } from 'react-router'

import { OnboardingGate } from '@/components/OnboardingGate'

import { App } from './App'
import { appRoutes } from './routes'

/** The React component type mounted for a route, or `undefined` for layout/no element. */
function elementType(route: RouteObject | undefined) {
  return route && isValidElement(route.element) ? route.element.type : undefined
}

const appShellRoute = appRoutes.find((route) => route.path === '/')
const shellChildren = appShellRoute?.children ?? []
const gateRoute = shellChildren.find((route) => elementType(route) === OnboardingGate)
const gatedPaths = (gateRoute?.children ?? []).map((route) => route.path)

describe('App routing', () => {
  it('routes / to the landing view inside the app shell', async () => {
    render(<App />)

    // The shell wraps every view: the wordmark is always present. Awaited so the
    // AuthProvider's mount-time session resume settles inside act().
    expect(await screen.findByRole('link', { name: 'Wren home' })).toBeInTheDocument()

    // / resolves to the landing hero.
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: /learn anything, in the right order/i,
      }),
    ).toBeInTheDocument()
  })
})

describe('App route tree gating', () => {
  it('nests the in-app authenticated routes under OnboardingGate', () => {
    expect(gateRoute).toBeDefined()
    expect(gatedPaths).toEqual(
      expect.arrayContaining([
        'dashboard',
        'user/:handle',
        'settings/connections',
        'roadmaps/:roadmapId/tree',
        'roadmaps/:roadmapId',
        '*',
      ]),
    )
  })

  it('does NOT wrap /authorize in OnboardingGate (structural OAuth-consent exemption)', () => {
    // US-GUARD-03: `/authorize` is exempt purely by placement. It is a direct
    // child of the shell (sibling of the gate), never inside the gate's subtree,
    // so an un-onboarded user mid agent-authorization is never bounced away.
    const authorizeRoute = shellChildren.find((route) => route.path === 'authorize')
    expect(authorizeRoute).toBeDefined()
    expect(gatedPaths).not.toContain('authorize')
  })

  it('leaves the public landing and auth routes ungated', () => {
    const publicPaths = shellChildren
      .filter((route) => route.index || route.path === 'auth')
      .map((route) => route.path ?? '(index)')
    expect(publicPaths).toEqual(expect.arrayContaining(['(index)', 'auth']))
    expect(gatedPaths).not.toContain('auth')
  })
})
