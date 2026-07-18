import { CTA_SETUP_MICROCOPY, HERO_HEADLINE, HERO_SUBHEAD } from '../constants'
import { HeroRoadmapVisual } from './HeroRoadmapVisual'
import { StartRoadmapButton } from './StartRoadmapButton'

/**
 * Above the fold: the single Fraunces display moment (H1), a plain-language
 * subhead that names the product category, the primary CTA, and the authentic
 * roadmap visual. On phones it stacks text → CTA → visual; from `lg` it splits
 * into two columns with the visual on the right.
 */
export function LandingHero() {
  return (
    <section className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
      <div>
        <h1 className="display-xl max-w-[15ch] text-balance text-foreground">
          {HERO_HEADLINE}
        </h1>
        <p className="mt-5 max-w-[46ch] text-[19px] leading-relaxed text-muted-foreground">
          {HERO_SUBHEAD}
        </p>
        <div className="mt-7">
          <StartRoadmapButton />
          <p className="mt-3 text-sm text-muted-foreground">{CTA_SETUP_MICROCOPY}</p>
        </div>
      </div>
      <HeroRoadmapVisual />
    </section>
  )
}
