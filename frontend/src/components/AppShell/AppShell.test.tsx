import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router'

import { buildAuthValue, renderWithAuth } from '@/test/auth-harness'
import { AppShell } from './AppShell'

/**
 * Render the shell as a layout route wrapping a child route, so the `<Outlet />`
 * has routed content to project (mirrors how App.tsx nests every view under it).
 */
function renderShell() {
  return renderWithAuth(
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<p>routed child content</p>} />
      </Route>
    </Routes>,
    { authValue: buildAuthValue({ status: 'anonymous' }) },
  )
}

describe('AppShell', () => {
  it('renders the top-bar chrome around the content region', () => {
    renderShell()
    expect(screen.getByRole('link', { name: 'Wren home' })).toBeInTheDocument()
  })

  it('projects the routed child through the Outlet inside the main content region', () => {
    renderShell()
    const main = screen.getByRole('main')
    expect(main).toContainElement(screen.getByText('routed child content'))
  })

  it('supplies only the page gutter, leaving width to the routed view (no sidebar)', () => {
    const { container } = renderShell()
    expect(container.querySelector('aside')).toBeNull()
    expect(screen.getByRole('main')).toHaveClass('px-6', 'py-8')
  })
})
