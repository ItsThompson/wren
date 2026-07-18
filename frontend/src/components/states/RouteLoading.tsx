import { Loader2 } from 'lucide-react'

/**
 * A neutral, full-viewport loading placeholder for route-level guards that run
 * above the views (e.g. while the session resolves from `loading`). The
 * per-view skeletons (`DashboardSkeleton`, `ConsentSpinner`) sit inside a
 * specific view's layout and are unsuitable here, so this is the shared surface
 * the onboarding/route guards render while `useAuth().status === 'loading'`.
 */
export function RouteLoading() {
  return (
    <div
      className="flex min-h-screen items-center justify-center bg-background"
      role="status"
      aria-label="Loading"
    >
      <Loader2 className="size-6 animate-spin text-muted-foreground" aria-hidden="true" />
    </div>
  )
}
