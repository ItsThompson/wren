import { HOW_IT_WORKS_STEPS } from '../constants'
import { HowItWorksStep } from './HowItWorksStep'

/**
 * The explainer band: three steps taking a visitor from "what I already know"
 * to a sequenced roadmap. Grotesque headings; no serif moment here.
 */
export function HowItWorks() {
  return (
    <section>
      <h2 className="text-2xl font-semibold text-foreground">How it works</h2>
      <ol className="mt-8 grid gap-5 sm:grid-cols-3">
        {HOW_IT_WORKS_STEPS.map((step, index) => (
          <HowItWorksStep key={step.title} step={step} index={index} />
        ))}
      </ol>
    </section>
  )
}
