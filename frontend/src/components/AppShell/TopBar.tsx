import { NavLink } from 'react-router'

import { cn } from '@/lib/utils'
import { AvatarMenu } from './AvatarMenu'
import { Wordmark } from './Wordmark'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground',
    isActive && 'bg-muted text-foreground',
  )

/**
 * The app's only chrome: a full-width top bar on card/bone with a hairline
 * bottom border and no sidebar (§8 App shell). Wordmark left; Dashboard,
 * Profile, and the avatar menu on the right.
 */
export function TopBar() {
  return (
    <header className="border-b border-border bg-card">
      <div className="flex items-center gap-4 px-6 py-3">
        <Wordmark />
        <nav className="ml-auto flex items-center gap-1">
          <NavLink to="/dashboard" className={navLinkClass}>
            Dashboard
          </NavLink>
          <NavLink to="/profile" className={navLinkClass}>
            Profile
          </NavLink>
        </nav>
        <AvatarMenu />
      </div>
    </header>
  )
}
