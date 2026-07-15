import type { Violation } from '@/lib/problem'
import { WarningBanner } from './WarningBanner'

interface ViolationListProps {
  violations: Violation[]
}

/**
 * The 422 publish/validate hard-block rendering (spec section 06, section 09
 * §10, US-ERR-02): the returned structural `violations` as readable ochre text,
 * each naming the rule, the human message, and the offending node ids. Meaning is
 * carried entirely by text (never color alone), so an author can fix every issue
 * in one pass and a screen-reader user gets the same information.
 */
export function ViolationList({ violations }: ViolationListProps) {
  const count = violations.length
  return (
    <WarningBanner
      title={`This draft can’t be published yet. Fix ${count} issue${count === 1 ? '' : 's'}:`}
    >
      <ul className="space-y-2">
        {violations.map((violation, index) => (
          <li key={`${violation.rule}:${violation.ids.join(',')}:${index}`}>
            <span className="font-mono text-xs text-foreground">{violation.rule}</span>{' '}
            <span className="text-foreground">{violation.message}</span>
            {violation.ids.length > 0 ? (
              <span className="mt-0.5 block font-mono text-xs text-muted-foreground">
                {violation.ids.join(', ')}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </WarningBanner>
  )
}
