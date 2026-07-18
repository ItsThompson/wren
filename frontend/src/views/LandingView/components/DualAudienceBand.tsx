import { DUAL_AUDIENCE_TRACKS } from '../constants'
import { AudienceTrack } from './AudienceTrack'

/**
 * Two parallel tracks on one roadmap: a human learns in the web app while an AI
 * agent follows the same plan. Conceptual framing only (no links or snippet).
 */
export function DualAudienceBand() {
  return (
    <section>
      <h2 className="text-2xl font-semibold text-foreground">One roadmap, two ways to use it</h2>
      <div className="mt-8 grid gap-5 sm:grid-cols-2">
        {DUAL_AUDIENCE_TRACKS.map((track) => (
          <AudienceTrack key={track.heading} track={track} />
        ))}
      </div>
    </section>
  )
}
