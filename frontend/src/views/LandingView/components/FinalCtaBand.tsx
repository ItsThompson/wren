import { StartRoadmapButton } from './StartRoadmapButton'

/**
 * The repeated closing CTA. The band stays calm (card stock) so the loud
 * terracotta primary CTA is the only Loud accent here, restating the promise
 * one more time before the footer.
 */
export function FinalCtaBand() {
  return (
    <section className="rounded-3xl border border-border bg-card px-8 py-14 text-center">
      <h2 className="mx-auto max-w-[20ch] text-2xl font-semibold text-foreground sm:text-3xl">
        Start learning in the right order.
      </h2>
      <div className="mt-7 flex justify-center">
        <StartRoadmapButton />
      </div>
    </section>
  )
}
