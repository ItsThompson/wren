/** Minimal shapes of the external-app JSON the e2e specs and seeding helpers read back. */

/** The authenticated session view returned by `/auth/refresh` (and register/login). */
export interface AuthenticatedUser {
  has_completed_onboarding: boolean
}

export interface NextItem {
  item_id: string
  why_now: string
  path_position: number | null
}

export interface NextResult {
  items: NextItem[]
  complete: boolean
  remaining_in_path: number
}

export interface ProgressSnapshot {
  checked_items: number
  percent: number
  checked_ids: string[]
  deadline: string | null
}
