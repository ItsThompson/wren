import { ArrowRight } from 'lucide-react'

import { Button } from '@/components/ui/button'

/**
 * Public landing (usewren.com): accent-forward. A Fraunces display-xl hero on
 * bone, one terracotta CTA, and a terracotta showcase block, with generous
 * whitespace (§8 Landing). No API calls: this is the loud showcase.
 */
export function LandingView() {
  return (
    <section className="reading-width py-16 sm:py-20">
      <h1 className="display-xl max-w-[15ch] text-balance text-foreground">
        Learn anything, in the right order.
      </h1>
      <p className="mt-5 max-w-[46ch] text-[19px] leading-relaxed text-muted-foreground">
        Wren turns what you already know into a roadmap of what comes next:
        sequenced, prerequisite-aware, and yours. Built for you and your AI
        agent to author together.
      </p>
      <div className="mt-7 flex flex-wrap gap-3">
        <Button size="lg">
          Start a roadmap
          <ArrowRight />
        </Button>
        <Button size="lg" variant="secondary">
          Browse examples
        </Button>
      </div>

      <div className="mt-14 rounded-3xl bg-primary px-12 py-16 text-center text-primary-foreground">
        <p className="mx-auto max-w-[22ch] font-serif text-[clamp(1.5rem,3.6vw,2.25rem)] font-medium leading-[1.14]">
          Every step just past what you know: challenging, but never out of
          reach.
        </p>
        <p className="mx-auto mt-4 max-w-[40ch] text-[15px] opacity-90">
          Roadmaps sequenced by your zone of proximal development.
        </p>
      </div>
    </section>
  )
}
