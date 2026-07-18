import { DualAudienceBand } from './components/DualAudienceBand'
import { FaqSection } from './components/FaqSection'
import { FinalCtaBand } from './components/FinalCtaBand'
import { HowItWorks } from './components/HowItWorks'
import { LandingFooter } from './components/LandingFooter'
import { LandingHero } from './components/LandingHero'
import { ValueBand } from './components/ValueBand'

/**
 * Public landing (usewren.com): a short long-scroll that explains the product.
 * A thin orchestrator composing presentational sections in order; the only
 * logic (the auth-aware primary CTA destination) lives in StartRoadmapButton.
 * Accent-forward yet calm per the in-tree design system: one Fraunces moment
 * (the hero H1), terracotta reserved for the primary CTAs and the value
 * showcase.
 */
export function LandingView() {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-20 sm:gap-28">
      <LandingHero />
      <HowItWorks />
      <ValueBand />
      <DualAudienceBand />
      <FaqSection />
      <FinalCtaBand />
      <LandingFooter />
    </div>
  )
}
