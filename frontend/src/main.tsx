import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import '../../shared/theme/fonts.css'
import '../../shared/theme/tokens.css'
import './globals.css'
import { App } from './App'

/**
 * Start the MSW worker before rendering when the mock harness is enabled
 * (`npm run dev:mock` sets `VITE_MOCK_API=true`). Unhandled requests bypass to
 * the network. In every other mode this is a no-op and the SPA talks to the
 * real backend.
 */
async function enableMocking(): Promise<void> {
  if (import.meta.env.VITE_MOCK_API !== 'true') return
  const { worker } = await import('./mocks/browser')
  await worker.start({ onUnhandledRequest: 'bypass' })
}

function renderApp(): void {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

// Render regardless of mock-start outcome; a failed worker (dev-only) is logged
// rather than left as an unhandled rejection or a blank screen.
enableMocking()
  .catch((error: unknown) => {
    console.error('[MSW] Failed to start the mock worker', error)
  })
  .finally(renderApp)
