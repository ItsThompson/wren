import { createBrowserRouter, RouterProvider } from 'react-router'

import { AppShell } from '@/components/AppShell'
import { LandingView } from '@/views/LandingView'
import { NotFoundView } from '@/views/NotFoundView'

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <LandingView /> },
      { path: '*', element: <NotFoundView /> },
    ],
  },
])

export function App() {
  return <RouterProvider router={router} />
}
