import * as Sentry from '@sentry/react'
import type { ReactNode } from 'react'

import { ErrorBoundaryFallback } from '@/components/ErrorBoundaryFallback/ErrorBoundaryFallback'

interface AppErrorBoundaryProps {
  children: ReactNode
}

export function AppErrorBoundary({ children }: AppErrorBoundaryProps) {
  return <Sentry.ErrorBoundary fallback={ErrorBoundaryFallback}>{children}</Sentry.ErrorBoundary>
}
