import { computeCountdown } from './deadline-countdown'

// A fixed "today" so the whole-day deltas are deterministic (2026-07-15 local).
const TODAY = new Date(2026, 6, 15)

describe('computeCountdown', () => {
  it('counts whole days remaining to a future deadline', () => {
    expect(computeCountdown('2026-07-27', TODAY)).toEqual({ days: 12, label: '12 days left' })
  })

  it('uses the singular for exactly one day left', () => {
    expect(computeCountdown('2026-07-16', TODAY)).toEqual({ days: 1, label: '1 day left' })
  })

  it('reports "Due today" when the deadline is today', () => {
    expect(computeCountdown('2026-07-15', TODAY)).toEqual({ days: 0, label: 'Due today' })
  })

  it('reports overdue for a past deadline (elapsed, no pacing signal)', () => {
    expect(computeCountdown('2026-07-12', TODAY)).toEqual({ days: -3, label: '3 days overdue' })
  })

  it('uses the singular for exactly one day overdue', () => {
    expect(computeCountdown('2026-07-14', TODAY)).toEqual({ days: -1, label: '1 day overdue' })
  })

  it('ignores the time of day (reduces both sides to the calendar date)', () => {
    // Late in the day still yields the same whole-day delta.
    const lateToday = new Date(2026, 6, 15, 23, 59)
    expect(computeCountdown('2026-07-17', lateToday)).toEqual({ days: 2, label: '2 days left' })
  })
})
