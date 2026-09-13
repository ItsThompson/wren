import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

function AuthSwitchProbe() {
  const [authValue, setAuthValue] = useState(buildAuthValue())
  return (
    <AuthContext.Provider value={authValue}>
      <SessionCacheBoundary>
        <CacheProbe />
      </SessionCacheBoundary>
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
})
