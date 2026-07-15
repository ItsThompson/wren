import { renderHook } from '@testing-library/react'

import { useAuth } from './useAuth'

describe('useAuth', () => {
  it('throws a clear error when used outside an AuthProvider', () => {
    // Suppress React's error-boundary console noise for the expected throw.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => renderHook(() => useAuth())).toThrow(
      'useAuth must be used within an AuthProvider',
    )
    spy.mockRestore()
  })
})
