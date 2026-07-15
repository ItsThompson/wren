import { computeCountdown } from '../deadline-countdown'

interface DeadlineCountdownProps {
  /** The caller's per-user deadline (`YYYY-MM-DD`), or null when none is set. */
  deadline: string | null
  /** Set (a date) or clear (null) the deadline; persists via `PUT /deadline`. */
  onSet: (deadline: string | null) => void
  /** Injectable "today" for deterministic tests; defaults to now. */
  today?: Date
}

/**
 * The roadmap-header deadline control:
 * an optional per-user deadline that renders a calm countdown in mono /
 * tabular-nums. It is a COUNTDOWN only: days left, due today, or overdue for a
 * past date, never a behind/ahead pacing signal. A native date
 * input sets/edits it and a ghost "Clear" removes it; both are editable anytime.
 */
export function DeadlineCountdown({ deadline, onSet, today = new Date() }: DeadlineCountdownProps) {
  const countdown = deadline ? computeCountdown(deadline, today) : null

  return (
    <div className="mt-4 flex items-center gap-3 font-mono text-[13px] text-muted-foreground">
      <span aria-hidden>Deadline</span>
      <input
        type="date"
        aria-label="Deadline"
        value={deadline ?? ''}
        onChange={(event) => onSet(event.target.value === '' ? null : event.target.value)}
        className="rounded-md border border-input bg-card px-2 py-1 tabular-nums text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      />
      {countdown ? (
        <span className="tabular-nums" data-testid="deadline-countdown">
          {countdown.label}
        </span>
      ) : null}
      {deadline ? (
        <button
          type="button"
          onClick={() => onSet(null)}
          className="underline-offset-2 hover:underline"
        >
          Clear
        </button>
      ) : null}
    </div>
  )
}
