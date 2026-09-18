import * as Sentry from '@sentry/react'
import { useRef, type ReactNode } from 'react'

import { ErrorBoundaryFallback } from '@/components/ErrorBoundaryFallback/ErrorBoundaryFallback'
import { applyRenderCaptureTags } from '@/observability/sentry'

interface AppErrorBoundaryProps {
  children: ReactNode
}

interface CauseSnapshotEntry {
  readonly error: Error
  readonly hadOwnCause: boolean
  readonly cause: unknown
}

function snapshotCauseChain(error: unknown): CauseSnapshotEntry[] {
  const entries: CauseSnapshotEntry[] = []
  const visited = new WeakSet<object>()
  let current: unknown = error
  while (current instanceof Error && !visited.has(current)) {
    visited.add(current)
    entries.push({
      error: current,
      hadOwnCause: Object.prototype.hasOwnProperty.call(current, 'cause'),
      cause: current.cause,
    })
    current = current.cause
  }
  return entries
}

function restoreCauseChain(entries: CauseSnapshotEntry[]): void {
  for (const { error, hadOwnCause, cause } of entries) {
    if (hadOwnCause) error.cause = cause
    else delete error.cause
  }
}

/**
 * The SDK ErrorBoundary's capture assigns a component-stack error to the
 * application error's `cause` chain. This boundary snapshots the chain before
 * capture and restores it after, so the error object application code sees is
 * never mutated: identity and the original cause chain survive capture.
 */
export function AppErrorBoundary({ children }: AppErrorBoundaryProps) {
  const causeSnapshots = useRef(new Map<unknown, CauseSnapshotEntry[]>())

  return (
    <Sentry.ErrorBoundary
      fallback={<ErrorBoundaryFallback />}
      beforeCapture={(scope, error) => {
        applyRenderCaptureTags(scope)
        causeSnapshots.current.set(error, snapshotCauseChain(error))
      }}
      onError={(error) => {
        const snapshot = causeSnapshots.current.get(error)
        if (snapshot) {
          restoreCauseChain(snapshot)
          causeSnapshots.current.delete(error)
        }
      }}
    >
      {children}
    </Sentry.ErrorBoundary>
  )
}
