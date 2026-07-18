import { HERO_HEADLINE } from '../constants'

/**
 * Slim brand footer: the Fraunces wordmark (the brand signature, exempt from
 * the one-serif-moment rule), a one-line tagline, the year, and the
 * t-industri.es parent-brand attribution. No nav links.
 */
export function LandingFooter() {
  const year = new Date().getFullYear()
  return (
    <footer className="border-t border-border pt-8 text-sm text-muted-foreground">
      <p className="font-serif text-xl font-medium lowercase tracking-[-0.01em] text-foreground">
        wren
      </p>
      <p className="mt-2">{HERO_HEADLINE}</p>
      <p className="mt-1">© {year} Wren</p>
      <p className="mt-1">
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
