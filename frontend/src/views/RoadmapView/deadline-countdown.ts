/**
 * Pure deadline-countdown derivation.
 *
 * The per-user deadline drives a COUNTDOWN only: the whole-day delta between
 * today and the target date. It is never a pacing signal: there is no
 * behind/ahead judgement and no effort forecast (section 15 out-of-scope). A
 * deadline in the past is allowed and renders as elapsed/overdue.
 */

export interface Countdown {
  /** Signed calendar-day delta: `> 0` days left, `0` due today, `< 0` overdue. */
  days: number
  /** Calm mono label, e.g. `"12 days left"` | `"Due today"` | `"3 days overdue"`. */
  label: string
}

const MS_PER_DAY = 86_400_000

/** Local-midnight timestamp for a calendar date (avoids DST/offset drift). */
function localMidnight(year: number, monthIndex: number, day: number): number {
  return new Date(year, monthIndex, day).getTime()
}

/**
 * Derive the countdown for a `YYYY-MM-DD` deadline relative to `today`. Both are
 * reduced to their local calendar date so the delta is whole days regardless of
 * the current time of day.
 */
export function computeCountdown(deadlineIso: string, today: Date): Countdown {
  const [year, month, day] = deadlineIso.split('-').map(Number)
  const target = localMidnight(year, month - 1, day)
  const start = localMidnight(today.getFullYear(), today.getMonth(), today.getDate())
  const days = Math.round((target - start) / MS_PER_DAY)

  if (days > 0) return { days, label: `${days} ${days === 1 ? 'day' : 'days'} left` }
  if (days === 0) return { days: 0, label: 'Due today' }
  const overdue = -days
  return { days, label: `${overdue} ${overdue === 1 ? 'day' : 'days'} overdue` }
}
