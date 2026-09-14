import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import useSWR from 'swr'
import { describe, expect, it } from 'vitest'

import { AuthContext } from '@/auth/auth-context'
import { buildAuthUser, buildAuthValue } from '@/test/auth-harness'
import { SessionCacheBoundary } from './SessionCacheBoundary'

function CacheProbe() {
  const { data, mutate } = useSWR<string>('private-document', null)
  return (
    <>
      <span data-testid="cached-value">{data ?? 'empty'}</span>
      <button onClick={() => void mutate('private data', { revalidate: false })}>seed</button>
    </>
  )
}

function AuthSwitchProbe({
  initialCache,
  withRouter = false,
}: {
  initialCache?: Map<string, { data: string }>
  withRouter?: boolean
}) {
  const [authValue, setAuthValue] = useState(buildAuthValue())
  const content = withRouter ? (
    <RouterProvider router={createMemoryRouter([{ path: '/', element: <CacheProbe /> }])} />
  ) : (
    <CacheProbe />
  )
  return (
    <AuthContext.Provider value={authValue}>
      <SessionCacheBoundary initialCache={initialCache}>{content}</SessionCacheBoundary>
      <button
        onClick={() =>
          setAuthValue(
            buildAuthValue({
              status: 'authenticated',
              user: buildAuthUser({ id: 'user-2' }),
            }),
          )
        }
      >
        switch account
      </button>
    </AuthContext.Provider>
  )
}

describe('SessionCacheBoundary', () => {
  it('drops cached data when the auth identity changes', async () => {
    const user = userEvent.setup()
    render(<AuthSwitchProbe />)

    await user.click(screen.getByRole('button', { name: 'seed' }))
    expect(screen.getByTestId('cached-value')).toHaveTextContent('private data')

    await user.click(screen.getByRole('button', { name: 'switch account' }))
    expect(screen.getByTestId('cached-value')).toHaveTextContent('empty')
  })

  it('consumes a supplied cache only for its initial identity', async () => {
    const user = userEvent.setup()
    const initialCache = new Map([['private-document', { data: 'seeded data' }]])
    render(<AuthSwitchProbe initialCache={initialCache} />)

    expect(screen.getByTestId('cached-value')).toHaveTextContent('seeded data')
    await user.click(screen.getByRole('button', { name: 'switch account' }))
    expect(screen.getByTestId('cached-value')).toHaveTextContent('empty')
  })

  it('keeps router consumers mounted across an identity transition', async () => {
    const user = userEvent.setup()
    render(<AuthSwitchProbe withRouter />)

    await user.click(screen.getByRole('button', { name: 'switch account' }))
    expect(screen.getByTestId('cached-value')).toHaveTextContent('empty')
  })
})
