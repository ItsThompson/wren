import { Link, useNavigate } from 'react-router'
import { LayoutDashboard, LogOut, Plug, User } from 'lucide-react'

import { useAuth } from '@/auth'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

/**
 * Account control on the top bar. While the session resolves it renders nothing;
 * anonymous visitors get a "Log in" link; authenticated users get the terracotta
 * avatar menu with their username, account destinations, and logout.
 */
export function AvatarMenu() {
  const { status, user, logout } = useAuth()
  const navigate = useNavigate()

  if (status === 'loading') {
    return null
  }

  if (status === 'anonymous' || user === null) {
    return (
      <Link
        to="/auth"
        className="rounded-md px-2.5 py-1.5 text-sm font-medium text-foreground hover:bg-muted"
      >
        Log in
      </Link>
    )
  }

  const handleLogout = async () => {
    await logout()
    navigate('/')
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Open account menu"
        className="grid size-[30px] place-items-center rounded-full bg-primary text-primary-foreground"
      >
        <User className="size-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-44">
        <DropdownMenuLabel>{user.username}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/dashboard">
            <LayoutDashboard />
            Dashboard
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to={`/user/${user.username}`}>
            <User />
            Your profile
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/settings/connections">
            <Plug />
            Connected agents
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={handleLogout}>
          <LogOut />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
