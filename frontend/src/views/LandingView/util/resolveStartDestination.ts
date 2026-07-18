import type { AuthStatus } from '@/auth'

/**
 * Where "Start a roadmap" sends a visitor once the session has resolved: an
 * authenticated visitor goes straight to their dashboard, anyone else goes to
 * signup (the register form, via `?mode=register`). The `loading` state is
 * never passed here; the hook gates it (see `useStartDestination`).
 */
export function resolveStartDestination(status: Exclude<AuthStatus, 'loading'>): string {
  return status === 'authenticated' ? '/dashboard' : '/auth?mode=register'
}
