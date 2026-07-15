import { Check, Circle, Lock, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router'

import { NODE_WIDTH } from '../constants'
import { NODE_STATE, type NodeState } from '../types'

interface DagNodeCardProps {
  title: string
  state: NodeState
  href: string
}

/**
 * Per-state presentation. State is conveyed by color AND icon (distinct shapes:
 * check / circle / lock), never color alone (spec section 09 accessibility); the
 * state word also rides in the link's accessible name for screen readers.
 */
const STATE_PRESENTATION: Record<
  NodeState,
  { icon: LucideIcon; className: string; iconClassName: string; label: string }
> = {
  [NODE_STATE.Done]: {
    icon: Check,
    className: 'border-success/60 bg-success/10',
    iconClassName: 'text-success',
    label: 'done',
  },
  [NODE_STATE.Available]: {
    icon: Circle,
    className: 'border-primary bg-card ring-2 ring-primary',
    iconClassName: 'text-primary',
    label: 'available',
  },
  [NODE_STATE.Locked]: {
    icon: Lock,
    className: 'border-border bg-muted opacity-60',
    iconClassName: 'text-muted-foreground',
    label: 'locked',
  },
}

/**
 * One subsection rendered as a tree node. The whole node is a
 * real `<Link>` to the subsection in the list view (frontend rule: links over
 * navigation handlers, so cmd/middle-click and hover-preview work). Soft-state
 * shows as color + icon; there is NO gating (a locked node is still a live link)
 * and NO progress bar. `data-state` is a stable hook for the state contract.
 */
export function DagNodeCard({ title, state, href }: DagNodeCardProps) {
  const { icon: Icon, className, iconClassName, label } = STATE_PRESENTATION[state]
  return (
    <Link
      to={href}
      data-state={state}
      aria-label={`${title} (${label})`}
      style={{ width: NODE_WIDTH }}
      className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium text-foreground no-underline transition-colors hover:border-primary ${className}`}
    >
      <Icon aria-hidden className={`size-4 shrink-0 ${iconClassName}`} />
      <span className="truncate">{title}</span>
    </Link>
  )
}
