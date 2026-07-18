import { FOOTER_TAGLINE } from '../constants'

/**
 * Slim brand footer: the Fraunces wordmark (the brand signature, exempt from
 * the one-serif-moment rule), a one-line tagline, and the year. No nav links.
 */
export function LandingFooter() {
  const year = new Date().getFullYear()
  return (
    <footer className="border-t border-border pt-8 text-sm text-muted-foreground">
      <p className="font-serif text-xl font-medium lowercase tracking-[-0.01em] text-foreground">
        wren
      </p>
      <p className="mt-2">{FOOTER_TAGLINE}</p>
      <p className="mt-1">© {year} Wren</p>
    </footer>
  )
}
