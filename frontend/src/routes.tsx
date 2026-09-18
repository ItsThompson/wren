import type { RouteObject } from 'react-router'

import { AppShell } from '@/components/AppShell'
import { ErrorBoundaryFallback } from '@/components/ErrorBoundaryFallback'
import { OnboardingGate } from '@/components/OnboardingGate'
import { PageTitle } from '@/components/PageTitle'
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
 * `/authorize` lives OUTSIDE the `OnboardingGate` and the in-app
 * authenticated routes live inside it, without rendering the views.
 */
export const appRoutes: RouteObject[] = [
  {
    // Chrome-free, full-screen: mounted OUTSIDE `AppShell` (no TopBar/gutter).
    // Its own guard bounces onboarded/anonymous users; the wizard renders only
    // for a signed-in, un-onboarded user.
    path: '/onboarding',
    errorElement: <ErrorBoundaryFallback />,
    element: (
      <PageTitle title="Get started">
        <OnboardingRouteGuard>
          <OnboardingView />
        </OnboardingRouteGuard>
      </PageTitle>
    ),
  },
  {
    path: '/',
    errorElement: <ErrorBoundaryFallback />,
    element: <AppShell />,
    children: [
      // Ungated (public or exempt). `/authorize` is the OAuth-consent surface:
      // its placement OUTSIDE `OnboardingGate` is the mechanism that keeps
      // an un-onboarded user mid agent-authorization from being bounced away.
      { index: true, element: <PageTitle><LandingView /></PageTitle> },
      {
        path: 'auth',
        element: (
          <PageTitle title="Log in">
            <AuthView />
          </PageTitle>
        ),
      },
      { path: 'authorize', element: <PageTitle title="Authorize agent"><ConsentView /></PageTitle> },

      // Gated: an authenticated, un-onboarded user is redirected to /onboarding
      // before the matched view mounts.
      {
        element: <OnboardingGate />,
        children: [
          { path: 'dashboard', element: <PageTitle title="Dashboard"><DashboardView /></PageTitle> },
          { path: 'user/:handle', element: <PageTitle title="Profile"><ProfileView /></PageTitle> },
          {
            path: 'settings/connections',
            element: <PageTitle title="Connected agents"><ConnectedClientsView /></PageTitle>,
          },
          {
            path: 'roadmaps/:roadmapId/tree',
            element: <PageTitle title="Roadmap"><TreeView /></PageTitle>,
          },
          {
            path: 'roadmaps/:roadmapId',
            element: <PageTitle title="Roadmap"><RoadmapView /></PageTitle>,
          },
          { path: '*', element: <PageTitle title="Page not found"><NotFoundView /></PageTitle> },
        ],
      },
    ],
  },
]
