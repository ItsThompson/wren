import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useArchivedProgressRefresh } from './useArchivedProgressRefresh'

describe('useArchivedProgressRefresh', () => {
  it('holds tracking closed while a published-to-archived read refreshes', async () => {
    const refreshProgress = vi.fn(() => Promise.resolve())
    const invalidateProgress = vi.fn(() => Promise.resolve())
    const { result, rerender } = renderHook(
      ({ status }: { status: 'published' | 'archived' }) =>
        useArchivedProgressRefresh(status, refreshProgress, invalidateProgress),
      { initialProps: { status: 'published' } },
    )

    expect(result.current).toBe(false)
    rerender({ status: 'archived' })

    expect(result.current).toBe(true)
    await waitFor(() => expect(result.current).toBe(false))
    expect(refreshProgress).toHaveBeenCalledOnce()
    expect(invalidateProgress).toHaveBeenCalledOnce()
  })

  it('gates an initially archived mount until cached progress is invalidated and reread', async () => {
    let resolveRefresh: (() => void) | undefined
    const refreshProgress = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveRefresh = resolve
        }),
    )
    const invalidateProgress = vi.fn(() => Promise.resolve())
    const { result } = renderHook(() =>
      useArchivedProgressRefresh('archived', refreshProgress, invalidateProgress),
    )

    expect(result.current).toBe(true)
    await waitFor(() => {
      expect(invalidateProgress).toHaveBeenCalledOnce()
      expect(refreshProgress).toHaveBeenCalledOnce()
    })
    expect(result.current).toBe(true)

    resolveRefresh?.()
    await waitFor(() => expect(result.current).toBe(false))
  })

  it.each(['success', 'failure'])(
    'releases an initially archived gate after StrictMode replay and refresh %s',
    async (outcome) => {
      const refreshProgress = vi.fn(async () => {
        if (outcome === 'failure') throw new Error('read failed')
      })
      const invalidateProgress = vi.fn(async () => undefined)
      const { result } = renderHook(
        () => useArchivedProgressRefresh('archived', refreshProgress, invalidateProgress),
        { reactStrictMode: true },
      )

      expect(result.current).toBe(true)
      await waitFor(() => expect(refreshProgress).toHaveBeenCalled())
      expect(invalidateProgress).toHaveBeenCalled()
      await waitFor(() => expect(result.current).toBe(false))
    },
  )

  it('releases the gate when the authoritative read fails', async () => {
    const refreshProgress = vi.fn(() => Promise.reject(new Error('read failed')))
    const invalidateProgress = vi.fn(() => Promise.resolve())
    const { result, rerender } = renderHook(
      ({ status }: { status: 'published' | 'archived' }) =>
        useArchivedProgressRefresh(status, refreshProgress, invalidateProgress),
      { initialProps: { status: 'published' } },
    )

    rerender({ status: 'archived' })
    await waitFor(() => expect(result.current).toBe(false))
  })
})
