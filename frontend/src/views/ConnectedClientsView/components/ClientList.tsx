import { ClientRow } from './ClientRow'
import type { ConnectedClient } from '../types'

interface ClientListProps {
  clients: ConnectedClient[]
  onRevoke: (clientId: string) => Promise<boolean>
}

/** The list of connected agents; each row owns its own confirm-gated revoke. */
export function ClientList({ clients, onRevoke }: ClientListProps) {
  return (
    <ul className="flex flex-col gap-3">
      {clients.map((client) => (
        <ClientRow key={client.client_id} client={client} onRevoke={onRevoke} />
      ))}
    </ul>
  )
}
