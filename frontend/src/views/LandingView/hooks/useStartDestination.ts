import { useAuth } from '@/auth'
import type { AuthStatus } from '@/auth'
import { resolveStartDestination } from '../util/resolveStartDestination'

/**
 * Auth-aware destination for the primary CTA. While the session is still
 * resolving (`loading`), `destination` is null so the CTA can render disabled
 * rather than briefly pointing a returning authenticated visitor at signup.
 */
export function useStartDestination(): { status: AuthStatus; destination: string | null } {
  const { status } = useAuth()
  const destination = status === 'loading' ? null : resolveStartDestination(status)
  return { status, destination }
}
