import { useState } from 'react'

import { Button } from '@/components/ui/button'
import type { ConnectedClient } from '../types'

/** Formats the last-authorized timestamp as a plain, locale-aware date. */
const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

/**
 * The revoke flow as a single state machine, so impossible combinations (e.g.
 * `revoking` without having entered the confirm gate) are unrepresentable. Used
 * only by this component, so it is co-located here rather than in a shared
 * types module.
 */
type RevokeStatus =
  | { phase: 'idle' }
  | { phase: 'confirming' }
  | { phase: 'revoking' }
  | { phase: 'error'; message: string }

interface ClientRowProps {
  client: ConnectedClient
  onRevoke: (clientId: string) => Promise<boolean>
}

/**
 * One connected agent: its name, when it was last authorized, and the scopes it
 * holds. Revoke is destructive, so it is confirm-gated: the
 * first click reveals a brick Confirm plus a Cancel. On success the parent drops
 * the row; a failure surfaces an inline message.
 */
export function ClientRow({ client, onRevoke }: ClientRowProps) {
  const [status, setStatus] = useState<RevokeStatus>({ phase: 'idle' })

  // The confirm/cancel pair stays visible from the confirm gate through the
  // in-flight revoke; `isRevoking` disables it and swaps the label.
  const isConfirming = status.phase === 'confirming' || status.phase === 'revoking'
  const isRevoking = status.phase === 'revoking'

  const handleRevoke = async () => {
    setStatus({ phase: 'revoking' })
    const ok = await onRevoke(client.client_id)
    if (!ok) {
      // On success the row unmounts; only a failure needs local recovery.
      setStatus({ phase: 'error', message: 'Could not revoke this agent. Please try again.' })
    }
  }

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border bg-card p-5 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="font-medium text-foreground">{client.client_name}</p>
        <p className="mt-1 font-mono text-xs text-muted-foreground">
          Last authorized {dateFormatter.format(new Date(client.last_authorized))}
        </p>
        {client.scopes.length > 0 ? (
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {client.scopes.map((scope) => (
              <li
                key={scope}
                className="rounded-md bg-secondary px-2 py-0.5 font-mono text-xs text-secondary-foreground"
              >
                {scope}
              </li>
            ))}
          </ul>
        ) : null}
        {status.phase === 'error' ? (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {status.message}
          </p>
        ) : null}
      </div>

      <div className="flex shrink-0 gap-2">
        {isConfirming ? (
          <>
            <Button variant="destructive" onClick={handleRevoke} disabled={isRevoking}>
              {isRevoking ? 'Revoking...' : 'Confirm revoke'}
            </Button>
            <Button variant="ghost" onClick={() => setStatus({ phase: 'idle' })} disabled={isRevoking}>
              Cancel
            </Button>
          </>
        ) : (
          <Button variant="outline" onClick={() => setStatus({ phase: 'confirming' })}>
            Revoke
          </Button>
        )}
      </div>
    </li>
  )
}
