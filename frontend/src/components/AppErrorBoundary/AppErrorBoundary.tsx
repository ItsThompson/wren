import * as Sentry from '@sentry/react'
import type { ReactNode } from 'react'

import { ErrorBoundaryFallback } from '@/components/ErrorBoundaryFallback/ErrorBoundaryFallback'
import { RENDER_OPERATION } from '@/observability/sentry'

interface AppErrorBoundaryProps {
  children: ReactNode
}

export function AppErrorBoundary({ children }: AppErrorBoundaryProps) {
  return (
    <Sentry.ErrorBoundary
      fallback={ErrorBoundaryFallback}
      beforeCapture={(scope) => {
        scope.setTag('api.operation', RENDER_OPERATION)
        scope.setTag('api.failure_kind', 'internal')
      }}
    >
      {children}
    </Sentry.ErrorBoundary>
  )
}
