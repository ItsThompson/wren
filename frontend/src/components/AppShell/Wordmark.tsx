import { Link } from 'react-router'

/**
 * The one place the brand signs its name in Fraunces. Lowercase `wren`, tight
 * tracking, medium weight. Everything else in the UI is grotesque.
 */
export function Wordmark() {
  return (
    <Link
      to="/"
      aria-label="Wren home"
      className="font-serif text-[21px] font-medium leading-none tracking-[-0.01em] lowercase text-foreground"
    >
      wren
    </Link>
  )
}
