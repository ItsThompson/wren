import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { buildAuthUser, buildAuthValue, renderWithAuth } from '@/test/auth-harness'
import { AvatarMenu } from './AvatarMenu'

describe('AvatarMenu', () => {
  it('shows a login link when anonymous', () => {
    renderWithAuth(<AvatarMenu />, { authValue: buildAuthValue({ status: 'anonymous' }) })

    const login = screen.getByRole('link', { name: 'Log in' })
    expect(login).toHaveAttribute('href', '/auth')
    expect(screen.queryByRole('button', { name: 'Open account menu' })).not.toBeInTheDocument()
  })

  it('renders nothing while the session is loading', () => {
    const { container } = renderWithAuth(<AvatarMenu />, {
      authValue: buildAuthValue({ status: 'loading' }),
    })
    expect(container).toBeEmptyDOMElement()
  })

  it('is closed until the avatar trigger is clicked when authenticated', () => {
    renderWithAuth(<AvatarMenu />, {
      authValue: buildAuthValue({ status: 'authenticated', user: buildAuthUser() }),
    })

    expect(screen.getByRole('button', { name: 'Open account menu' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument()
  })

  it('opens the menu showing the handle, account links, and logout', async () => {
    const user = userEvent.setup()
    renderWithAuth(<AvatarMenu />, {
      authValue: buildAuthValue({ status: 'authenticated', user: buildAuthUser({ username: 'ada' }) }),
    })

    await user.click(screen.getByRole('button', { name: 'Open account menu' }))

    expect(await screen.findByText('ada')).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /dashboard/i })).toHaveAttribute(
      'href',
      '/dashboard',
    )
    expect(screen.getByRole('menuitem', { name: /your profile/i })).toHaveAttribute(
      'href',
      '/user/ada',
    )
    expect(screen.getByRole('menuitem', { name: /connected agents/i })).toHaveAttribute(
      'href',
      '/settings/connections',
    )
    expect(screen.getByRole('menuitem', { name: /log out/i })).toBeInTheDocument()
  })

  it('calls logout when the logout item is selected', async () => {
    const user = userEvent.setup()
    const logout = vi.fn(async () => {})
    renderWithAuth(<AvatarMenu />, {
      authValue: buildAuthValue({ status: 'authenticated', user: buildAuthUser(), logout }),
    })

    await user.click(screen.getByRole('button', { name: 'Open account menu' }))
    await user.click(await screen.findByRole('menuitem', { name: /log out/i }))

    expect(logout).toHaveBeenCalledOnce()
  })
})
