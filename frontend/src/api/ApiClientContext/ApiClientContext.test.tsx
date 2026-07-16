import { render, renderHook } from '@testing-library/react'

import { ApiClientProvider, usePublicClient, useSessionClient } from './ApiClientContext'
import type { ApiClient, SessionClient } from '../client'

interface CapturedClients {
  session: SessionClient
  public: ApiClient
}

describe('ApiClientProvider', () => {
  it('memoizes clients on baseUrl: reuses instances when unchanged, rebuilds both when changed', () => {
    let current: CapturedClients | null = null
    function Capture() {
      current = { session: useSessionClient(), public: usePublicClient() }
      return null
    }

    const { rerender } = render(
      <ApiClientProvider baseUrl="https://api.test">
        <Capture />
      </ApiClientProvider>,
    )
    const first = current!

    rerender(
      <ApiClientProvider baseUrl="https://api.test">
        <Capture />
      </ApiClientProvider>,
    )
    const afterSameBaseUrl = current!

    rerender(
      <ApiClientProvider baseUrl="https://other.test">
        <Capture />
      </ApiClientProvider>,
    )
    const afterChangedBaseUrl = current!

    // Unchanged baseUrl reuses both instances (shared refresh lock).
    expect(afterSameBaseUrl.session).toBe(first.session)
    expect(afterSameBaseUrl.public).toBe(first.public)
    // Changed baseUrl rebuilds both.
    expect(afterChangedBaseUrl.session).not.toBe(first.session)
    expect(afterChangedBaseUrl.public).not.toBe(first.public)
  })
})

describe('useSessionClient', () => {
  it('throws a clear error when used outside an ApiClientProvider', () => {
    // Suppress React's error-boundary console noise for the expected throw.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => renderHook(() => useSessionClient())).toThrow(
      'useSessionClient must be used within an ApiClientProvider',
    )
    spy.mockRestore()
  })
})

describe('usePublicClient', () => {
  it('throws a clear error when used outside an ApiClientProvider', () => {
    // Suppress React's error-boundary console noise for the expected throw.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => renderHook(() => usePublicClient())).toThrow(
      'usePublicClient must be used within an ApiClientProvider',
    )
    spy.mockRestore()
  })
})
