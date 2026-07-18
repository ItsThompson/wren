import { VALUE_BENEFIT, VALUE_FOOTNOTE, VALUE_PULL_QUOTE } from '../constants'

/**
 * The reframed ZPD showcase. The short pull-quote sits Loud on the terracotta
 * fill in the GROTESQUE display scale (the hero H1 stays the page's only
 * Fraunces moment); the benefit copy and the ZPD footnote stay calm,
 * ink-on-bone, beside the fill. No paragraph of reading copy on terracotta.
 */
export function ValueBand() {
  return (
    <section className="grid gap-8 lg:grid-cols-2 lg:items-center lg:gap-14">
      <blockquote className="rounded-3xl bg-primary px-10 py-12 text-primary-foreground">
        <p className="max-w-[18ch] text-[clamp(1.75rem,3.6vw,2.5rem)] font-semibold leading-[1.1] tracking-[-0.01em]">
          {VALUE_PULL_QUOTE}
        </p>
      </blockquote>
      <div>
        <p className="max-w-[42ch] text-lg leading-relaxed text-foreground">{VALUE_BENEFIT}</p>
        <p className="mt-4 text-sm text-muted-foreground">{VALUE_FOOTNOTE}</p>
      </div>
    </section>
  )
}
