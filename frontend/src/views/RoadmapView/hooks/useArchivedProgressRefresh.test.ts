import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useArchivedProgressRefresh } from './useArchivedProgressRefresh'

describe('useArchivedProgressRefresh', () => {
  it('holds tracking closed while a published-to-archived read refreshes', async () => {
    const refreshProgress = vi.fn(() => Promise.resolve())
    const { result, rerender } = renderHook(
      ({ status }: { status: 'published' | 'archived' }) =>
        useArchivedProgressRefresh(status, refreshProgress),
      { initialProps: { status: 'published' } },
    )

    expect(result.current).toBe(false)
    rerender({ status: 'archived' })

    expect(result.current).toBe(true)
    await waitFor(() => expect(result.current).toBe(false))
    expect(refreshProgress).toHaveBeenCalledOnce()
  })

  it('releases the gate when the authoritative read fails', async () => {
    const refreshProgress = vi.fn(() => Promise.reject(new Error('read failed')))
    const { result, rerender } = renderHook(
      ({ status }: { status: 'published' | 'archived' }) =>
        useArchivedProgressRefresh(status, refreshProgress),
      { initialProps: { status: 'published' } },
    )

    rerender({ status: 'archived' })
    await waitFor(() => expect(result.current).toBe(false))
  })
})
