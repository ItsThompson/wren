import { createBrowserRouter, RouterProvider } from 'react-router'
import { SWRConfig } from 'swr'

import { ApiClientProvider, swrRevalidationPosture } from '@/api'
import { AuthProvider } from '@/auth'

import { appRoutes } from './routes'

const router = createBrowserRouter(appRoutes)

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
