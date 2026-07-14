import { Outlet } from 'react-router'

import { TopBar } from './TopBar'

/**
 * The frame every view renders inside: top bar + a content region. Views own
 * their own max-width (reading views center ~860px via `.reading-width`;
 * tree/dashboard go wider), so the shell only supplies the page gutter.
 */
export function AppShell() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopBar />
      <main className="flex-1 px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}
