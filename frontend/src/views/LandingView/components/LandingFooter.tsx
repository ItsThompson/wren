import { HERO_HEADLINE } from '../constants'

/**
 * Slim brand footer: the Fraunces wordmark (the brand signature, exempt from
 * the one-serif-moment rule), a one-line tagline, and the t-industri.es
 * parent-brand attribution. No nav links.
 */
export function LandingFooter() {
  return (
    <footer className="grid gap-6 border-t border-border pt-8 text-sm text-muted-foreground sm:grid-cols-3 sm:items-start">
      <p className="font-serif text-xl font-medium lowercase tracking-[-0.01em] text-foreground">
        wren
      </p>
      <p className="sm:justify-self-center sm:text-center">{HERO_HEADLINE}</p>
      <p className="sm:justify-self-end sm:text-right">
        A{' '}
        <a
          href="https://t-industri.es/"
          target="_blank"
          rel="noreferrer"
          className="text-primary underline-offset-4 hover:underline"
        >
          t-industri.es
        </a>{' '}
        project
      </p>
    </footer>
  )
}
