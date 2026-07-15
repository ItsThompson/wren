import { useState } from 'react'

import { Button } from '@/components/ui/button'
import type { ConnectedClient } from '../types'

/** Formats the last-authorized timestamp as a plain, locale-aware date. */
const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

interface ClientRowProps {
  client: ConnectedClient
  onRevoke: (clientId: string) => Promise<boolean>
}

/**
 * One connected agent: its name, when it was last authorized, and the scopes it
 * holds. Revoke is destructive, so it is confirm-gated (design language): the
 * first click reveals a brick Confirm plus a Cancel. On success the parent drops
 * the row; a failure surfaces an inline message.
 */
export function ClientRow({ client, onRevoke }: ClientRowProps) {
  const [confirming, setConfirming] = useState(false)
  const [revoking, setRevoking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleRevoke = async () => {
    setRevoking(true)
    setError(null)
    const ok = await onRevoke(client.client_id)
    if (!ok) {
      // On success the row unmounts; only a failure needs local recovery.
      setRevoking(false)
      setConfirming(false)
      setError('Could not revoke this agent. Please try again.')
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
        {error ? (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {error}
          </p>
        ) : null}
      </div>

      <div className="flex shrink-0 gap-2">
        {confirming ? (
          <>
            <Button variant="destructive" onClick={handleRevoke} disabled={revoking}>
              {revoking ? 'Revoking...' : 'Confirm revoke'}
            </Button>
            <Button variant="ghost" onClick={() => setConfirming(false)} disabled={revoking}>
              Cancel
            </Button>
          </>
        ) : (
          <Button variant="outline" onClick={() => setConfirming(true)}>
            Revoke
          </Button>
        )}
      </div>
    </li>
  )
}
