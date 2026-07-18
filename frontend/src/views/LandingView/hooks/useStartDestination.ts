import { useAuth } from '@/auth'
import { resolveStartDestination } from '../util/resolveStartDestination'

/**
 * Auth-aware destination for the primary CTA. While the session is still
 * resolving (`loading`), returns null so the CTA can render disabled rather
 * than briefly pointing a returning authenticated visitor at signup.
 */
export function useStartDestination(): string | null {
  const { status } = useAuth()
  return status === 'loading' ? null : resolveStartDestination(status)
}
