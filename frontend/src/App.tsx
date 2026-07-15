import { createBrowserRouter, RouterProvider } from 'react-router'
import { SWRConfig } from 'swr'

import { ApiClientProvider, swrRevalidationPosture } from '@/api'
import { AuthProvider } from '@/auth'
import { AppShell } from '@/components/AppShell'
import { AuthView } from '@/views/AuthView'
import { ConnectedClientsView } from '@/views/ConnectedClientsView'
import { ConsentView } from '@/views/ConsentView'
import { DashboardView } from '@/views/DashboardView'
import { LandingView } from '@/views/LandingView'
import { NotFoundView } from '@/views/NotFoundView'
import { ProfileView } from '@/views/ProfileView'
import { RoadmapView } from '@/views/RoadmapView'
import { TreeView } from '@/views/TreeView'

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <LandingView /> },
      { path: 'auth', element: <AuthView /> },
      { path: 'authorize', element: <ConsentView /> },
      { path: 'dashboard', element: <DashboardView /> },
      { path: 'user/:handle', element: <ProfileView /> },
      { path: 'settings/connections', element: <ConnectedClientsView /> },
      { path: 'roadmaps/:roadmapId/tree', element: <TreeView /> },
      { path: 'roadmaps/:roadmapId', element: <RoadmapView /> },
      { path: '*', element: <NotFoundView /> },
    ],
  },
])

/**
 * Same-origin by default (dev proxy + MSW); prod points at the API subdomain via
 * `VITE_API_BASE_URL`. Read once at the app root: the deployment base never
 * changes at runtime, and the shared clients bind to it here.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export function App() {
  return (
    <SWRConfig value={swrRevalidationPosture}>
      <ApiClientProvider baseUrl={API_BASE_URL}>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </ApiClientProvider>
    </SWRConfig>
  )
}
