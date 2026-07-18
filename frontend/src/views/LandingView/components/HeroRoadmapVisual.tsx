import { HERO_VISUAL_ALT } from '../constants'

/**
 * The hero's authentic product visual: a real screenshot of a Wren roadmap's
 * prerequisite graph, framed on card stock. Static (no motion); the descriptive
 * alt carries the full node labels the cropped raster clips.
 */
export function HeroRoadmapVisual() {
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
      <img
        src="/landing/roadmap-tree.png"
        alt={HERO_VISUAL_ALT}
        width={1300}
        height={1300}
        className="h-auto w-full"
      />
    </div>
  )
}
