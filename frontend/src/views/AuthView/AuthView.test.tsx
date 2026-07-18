import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'

import { buildAuthUser, buildAuthValue, renderWithAuth } from '@/test/auth-harness'
import { AuthView } from './AuthView'

describe('AuthView', () => {
  it('shows the login form by default', () => {
    renderWithAuth(<AuthView />)
    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument()
    expect(screen.queryByText('Username')).not.toBeInTheDocument()
  })

  it('switches to the register form', async () => {
    const user = userEvent.setup()
    renderWithAuth(<AuthView />)

    await user.click(screen.getByRole('button', { name: 'Create an account' }))

    expect(screen.getByRole('heading', { name: 'Join Wren' })).toBeInTheDocument()
    expect(screen.getByText('Username')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument()
  })

  it('opens the register form when the URL asks for register mode', () => {
    renderWithAuth(<AuthView />, { initialEntries: ['/auth?mode=register'] })

    expect(screen.getByRole('heading', { name: 'Join Wren' })).toBeInTheDocument()
    expect(screen.getByText('Username')).toBeInTheDocument()
  })

  it('still defaults to the login form when the mode param is absent', () => {
    renderWithAuth(<AuthView />, { initialEntries: ['/auth'] })

    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
    expect(screen.queryByText('Username')).not.toBeInTheDocument()
  })

  it('submits entered credentials to login', async () => {
    const login = vi.fn(async () => ({ ok: true }) as const)
    const user = userEvent.setup()
    renderWithAuth(<AuthView />, { authValue: buildAuthValue({ login }) })

    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'Str0ngPass')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(login).toHaveBeenCalledWith({ email: 'ada@example.com', password: 'Str0ngPass' })
  })

  it('shows a validation message when required fields are empty', async () => {
    const login = vi.fn(async () => ({ ok: true }) as const)
    const user = userEvent.setup()
    renderWithAuth(<AuthView />, { authValue: buildAuthValue({ login }) })

    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Enter your email and password.')
    expect(login).not.toHaveBeenCalled()
  })

  it('renders the generic message on a failed login', async () => {
    const login = vi.fn(async () => ({ ok: false, message: 'Invalid email or password.' }) as const)
    const user = userEvent.setup()
    renderWithAuth(<AuthView />, { authValue: buildAuthValue({ login }) })

    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Invalid email or password.'),
    )
  })

  it('attaches a field-level error to the offending register input', async () => {
    const register = vi.fn(async () => ({
      ok: false as const,
      message: 'An account with this email already exists.',
      fields: { email: 'This email is already registered.' },
    }))
    const user = userEvent.setup()
    renderWithAuth(<AuthView />, { authValue: buildAuthValue({ register }) })

    await user.click(screen.getByRole('button', { name: 'Create an account' }))
    await user.type(screen.getByLabelText('Username'), 'ada')
    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'Str0ngPass')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() =>
      expect(screen.getByText('This email is already registered.')).toBeInTheDocument(),
    )
  })

  it('does not duplicate register errors that are already attached to a field', async () => {
    const passwordError =
      'Password must be at least 8 characters and include an uppercase letter, a lowercase letter, and a digit.'
    const register = vi.fn(async () => ({
      ok: false as const,
      message: passwordError,
      fields: { password: passwordError },
    }))
    const user = userEvent.setup()
    renderWithAuth(<AuthView />, { authValue: buildAuthValue({ register }) })

    await user.click(screen.getByRole('button', { name: 'Create an account' }))
    await user.type(screen.getByLabelText('Username'), 'ada')
    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'password')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => expect(screen.getAllByText(passwordError)).toHaveLength(1))
    expect(screen.getByLabelText('Password')).toHaveFocus()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('redirects into the app once authenticated', () => {
    renderWithAuth(
      <Routes>
        <Route path="/auth" element={<AuthView />} />
        <Route path="/" element={<div>home</div>} />
      </Routes>,
      {
        authValue: buildAuthValue({ status: 'authenticated', user: buildAuthUser() }),
        initialEntries: ['/auth'],
      },
    )
    expect(screen.getByText('home')).toBeInTheDocument()
  })
})
