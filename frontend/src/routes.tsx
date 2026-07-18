import type { RouteObject } from 'react-router'

import { AppShell } from '@/components/AppShell'
import { OnboardingGate } from '@/components/OnboardingGate'
import { AuthView } from '@/views/AuthView'
import { ConnectedClientsView } from '@/views/ConnectedClientsView'
import { ConsentView } from '@/views/ConsentView'
import { DashboardView } from '@/views/DashboardView'
import { LandingView } from '@/views/LandingView'
import { NotFoundView } from '@/views/NotFoundView'
import { OnboardingRouteGuard, OnboardingView } from '@/views/OnboardingView'
import { ProfileView } from '@/views/ProfileView'
import { RoadmapView } from '@/views/RoadmapView'
import { TreeView } from '@/views/TreeView'

/**
 * The application route tree. Kept separate from `App` (the provider composition)
 * so a routing-config test can assert the structural invariants: notably that
 * `/authorize` lives OUTSIDE the `OnboardingGate` (US-GUARD-03) and the in-app
 * authenticated routes live inside it (US-GUARD-01), without rendering the views.
 */
export const appRoutes: RouteObject[] = [
  {
    // Chrome-free, full-screen: mounted OUTSIDE `AppShell` (no TopBar/gutter).
    // Its own guard bounces onboarded/anonymous users; the wizard renders only
    // for a signed-in, un-onboarded user.
    path: '/onboarding',
    element: (
      <OnboardingRouteGuard>
        <OnboardingView />
      </OnboardingRouteGuard>
    ),
  },
  {
    path: '/',
    element: <AppShell />,
    children: [
      // Ungated (public or exempt). `/authorize` is the OAuth-consent surface:
      // its placement OUTSIDE `OnboardingGate` is the mechanism for US-GUARD-03
      // (an un-onboarded user mid agent-authorization is never bounced away).
      { index: true, element: <LandingView /> },
      { path: 'auth', element: <AuthView /> },
      { path: 'authorize', element: <ConsentView /> },

      // Gated: an authenticated, un-onboarded user is redirected to /onboarding
      // before the matched view mounts (US-GUARD-01).
      {
        element: <OnboardingGate />,
        children: [
          { path: 'dashboard', element: <DashboardView /> },
          { path: 'user/:handle', element: <ProfileView /> },
          { path: 'settings/connections', element: <ConnectedClientsView /> },
          { path: 'roadmaps/:roadmapId/tree', element: <TreeView /> },
          { path: 'roadmaps/:roadmapId', element: <RoadmapView /> },
          { path: '*', element: <NotFoundView /> },
        ],
      },
    ],
  },
]
