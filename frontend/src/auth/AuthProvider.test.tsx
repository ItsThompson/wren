import { useState } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { handlers } from '@/mocks/handlers'
import { mockAuthUser } from '@/mocks/data'
import { AuthProvider } from './AuthProvider'
import { useAuth } from './useAuth'

const BASE = 'https://api.test'
const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function problem(status: number, body: Record<string, unknown>) {
  return HttpResponse.json(
    { type: 'https://usewren.com/errors/x', status, ...body },
    { status, headers: { 'content-type': 'application/problem+json' } },
  )
}

/** Surfaces the context so tests can drive and observe the session. */
function Probe() {
  const { status, user, login, register, logout } = useAuth()
  const [message, setMessage] = useState('')
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="user">{user?.username ?? 'none'}</span>
      <span data-testid="message">{message}</span>
      <button
        onClick={async () => {
          const result = await login({ email: 'ada@example.com', password: 'Str0ngPass' })
          if (!result.ok) setMessage(result.message)
        }}
      >
        login
      </button>
      <button
        onClick={async () => {
          const result = await register({
            username: 'ada',
            email: 'ada@example.com',
            password: 'Str0ngPass',
          })
          if (!result.ok) setMessage(result.fields?.email ?? result.message)
        }}
      >
        register
      </button>
      <button onClick={() => void logout()}>logout</button>
    </div>
  )
}

function renderProbe() {
  return render(
    <AuthProvider baseUrl={BASE}>
      <Probe />
    </AuthProvider>,
  )
}

async function waitForResolved() {
  await waitFor(() => expect(screen.getByTestId('status').textContent).not.toBe('loading'))
}

describe('AuthProvider', () => {
  it('resolves to anonymous when no session can be resumed', async () => {
    renderProbe()
    await waitForResolved()
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
    expect(screen.getByTestId('user')).toHaveTextContent('none')
  })

  it('resumes an existing session on mount via the refresh token', async () => {
    server.use(http.post('*/auth/refresh', () => HttpResponse.json(mockAuthUser)))
    renderProbe()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    expect(screen.getByTestId('user')).toHaveTextContent(mockAuthUser.username)
  })

  it('authenticates on a successful login', async () => {
    const user = userEvent.setup()
    renderProbe()
    await waitForResolved()

    await user.click(screen.getByRole('button', { name: 'login' }))

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    expect(screen.getByTestId('user')).toHaveTextContent(mockAuthUser.username)
  })

  it('surfaces the generic message on bad credentials', async () => {
    server.use(
      http.post('*/auth/login', () => problem(401, { code: 'UNAUTHORIZED', detail: 'Invalid email or password.' })),
    )
    const user = userEvent.setup()
    renderProbe()
    await waitForResolved()

    await user.click(screen.getByRole('button', { name: 'login' }))

    await waitFor(() =>
      expect(screen.getByTestId('message')).toHaveTextContent('Invalid email or password.'),
    )
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
  })

  it('surfaces a field-level conflict on register', async () => {
    server.use(
      http.post('*/auth/register', () =>
        problem(409, {
          code: 'CONFLICT',
          detail: 'An account with this email already exists.',
          fields: { email: 'This email is already registered.' },
        }),
      ),
    )
    const user = userEvent.setup()
    renderProbe()
    await waitForResolved()

    await user.click(screen.getByRole('button', { name: 'register' }))

    await waitFor(() =>
      expect(screen.getByTestId('message')).toHaveTextContent('This email is already registered.'),
    )
  })

  it('returns to anonymous after logout', async () => {
    server.use(http.post('*/auth/refresh', () => HttpResponse.json(mockAuthUser)))
    const user = userEvent.setup()
    renderProbe()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))

    await user.click(screen.getByRole('button', { name: 'logout' }))

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('anonymous'))
    expect(screen.getByTestId('user')).toHaveTextContent('none')
  })

  it('clears the local session even when the logout request fails', async () => {
    server.use(
      http.post('*/auth/refresh', () => HttpResponse.json(mockAuthUser)),
      http.post('*/auth/logout', () => HttpResponse.error()),
    )
    const user = userEvent.setup()
    renderProbe()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))

    await user.click(screen.getByRole('button', { name: 'logout' }))

    // A rejected logout POST must still drop the client to anonymous (try/finally).
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('anonymous'))
  })
})
