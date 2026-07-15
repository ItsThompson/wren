import { NavLink } from 'react-router'

import { useAuth } from '@/auth'
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
 * bottom border and no sidebar. Wordmark left; the personal
 * Dashboard + Profile destinations and the avatar menu on the right. The
 * personal links resolve the signed-in user's handle, so they show only when
 * authenticated; anonymous visitors get just the wordmark and the log-in control.
 */
export function TopBar() {
  const { status, user } = useAuth()
  const isAuthenticated = status === 'authenticated' && user !== null

  return (
    <header className="border-b border-border bg-card">
      <div className="flex items-center gap-4 px-6 py-3">
        <Wordmark />
        <div className="ml-auto flex items-center gap-1">
          {isAuthenticated && (
            <nav className="flex items-center gap-1">
              <NavLink to="/dashboard" className={navLinkClass}>
                Dashboard
              </NavLink>
              <NavLink to={`/user/${user.username}`} className={navLinkClass}>
                Profile
              </NavLink>
            </nav>
          )}
          <AvatarMenu />
        </div>
      </div>
    </header>
  )
}
