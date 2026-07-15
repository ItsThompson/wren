import { createBrowserRouter, RouterProvider } from 'react-router'

import { AuthProvider } from '@/auth'
import { AppShell } from '@/components/AppShell'
import { AuthView } from '@/views/AuthView'
import { ConnectedClientsView } from '@/views/ConnectedClientsView'
import { ConsentView } from '@/views/ConsentView'
import { LandingView } from '@/views/LandingView'
import { NotFoundView } from '@/views/NotFoundView'
import { RoadmapView } from '@/views/RoadmapView'

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <LandingView /> },
      { path: 'auth', element: <AuthView /> },
      { path: 'authorize', element: <ConsentView /> },
      { path: 'settings/connections', element: <ConnectedClientsView /> },
      { path: 'roadmaps/:roadmapId', element: <RoadmapView /> },
      { path: '*', element: <NotFoundView /> },
    ],
  },
])

export function App() {
  return (
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  )
}
