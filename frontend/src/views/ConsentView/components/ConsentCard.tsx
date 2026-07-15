import { ShieldCheck } from 'lucide-react'

import { Button } from '@/components/ui/button'

/**
 * Plain-language labels for the scopes the AS grants. The raw scope
 * token is shown alongside so the grant is legible and honest; an unknown scope
 * falls back to its token.
 */
const SCOPE_LABELS: Record<string, string> = {
  'roadmaps:read': 'Read your roadmaps',
  'roadmaps:write': 'Create and edit your roadmaps',
  'progress:write': 'Update your learning progress',
}

interface ConsentCardProps {
  clientName: string
  userName: string
  scopes: string[]
  pending: boolean
  error: string | null
  onApprove: () => void
  onDeny: () => void
}

/**
 * The OAuth consent card: branded, calm, centered. The
 * one Fraunces moment states "<Agent> wants to act as <you>," the requested
 * scopes render as a plain list, and the decision is a primary Authorize plus a
 * ghost Deny. The trust moment: quiet and legible, not loud.
 */
export function ConsentCard({
  clientName,
  userName,
  scopes,
  pending,
  error,
  onApprove,
  onDeny,
}: ConsentCardProps) {
  return (
    <section className="reading-width max-w-[28rem] py-16">
      <div className="rounded-lg border border-border bg-card p-6 sm:p-8">
        <div className="flex items-center gap-2 text-muted-foreground">
          <ShieldCheck className="size-5" aria-hidden="true" />
          <span className="text-sm font-medium">Authorize access</span>
        </div>

        <h1 className="display-m mt-4 text-foreground">
          <span className="font-semibold">{clientName}</span> wants to act as{' '}
          <span className="font-semibold">{userName}</span>
        </h1>

        <p className="mt-5 text-sm text-muted-foreground">
          If you authorize, this agent will be able to:
        </p>
        <ul className="mt-3 flex flex-col gap-2.5">
          {scopes.map((scope) => (
            <li key={scope} className="flex flex-col">
              <span className="text-sm text-foreground">{SCOPE_LABELS[scope] ?? scope}</span>
              <span className="font-mono text-xs text-muted-foreground">{scope}</span>
            </li>
          ))}
        </ul>

        {error ? (
          <p role="alert" className="mt-5 text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <div className="mt-8 flex flex-col gap-2">
          <Button onClick={onApprove} disabled={pending}>
            {pending ? 'Authorizing...' : 'Authorize'}
          </Button>
          <Button variant="ghost" onClick={onDeny} disabled={pending}>
            Deny
          </Button>
        </div>
      </div>
    </section>
  )
}
