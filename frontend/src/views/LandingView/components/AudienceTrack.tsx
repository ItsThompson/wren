import type { AudienceTrackData } from '../types'

interface AudienceTrackProps {
  track: AudienceTrackData
}

/**
 * One dual-audience track: an icon, a heading, and a one-line description.
 * Conceptual only: no links, code, or connect CTA (MCP docs are out of scope).
 */
export function AudienceTrack({ track }: AudienceTrackProps) {
  const { icon: Icon, heading, body } = track
  return (
    <div className="rounded-2xl border border-border bg-card p-6">
      <div className="flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-full bg-accent text-accent-foreground">
          <Icon aria-hidden className="size-5" />
        </span>
        <h3 className="text-lg font-semibold text-foreground">{heading}</h3>
      </div>
      <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">{body}</p>
    </div>
  )
}
