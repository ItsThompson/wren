import { setupWorker } from 'msw/browser'

import { handlers } from './handlers'

/**
 * Browser MSW worker for the zero-backend dev harness. Started from `main.tsx`
 * only when `VITE_MOCK_API=true` (`npm run dev:mock`). Unhandled requests are
 * bypassed so anything the handlers don't cover still hits the network.
 */
export const worker = setupWorker(...handlers)
