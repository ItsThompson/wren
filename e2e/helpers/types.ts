/** Minimal shapes of the external-app JSON the seeding helper reads back. */

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
