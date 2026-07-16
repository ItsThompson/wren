import type { ReactNode } from 'react'
import { renderHook } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, vi } from 'vitest'
import type { MockInstance } from 'vitest'

import { useHashScroll } from './useHashScroll'

/**
 * A bare `MemoryRouter` wrapper starting at `/roadmaps/x{hash}`, so
 * `useLocation().hash` resolves to `hash`. `useHashScroll` reads only the router
 * location, so it needs no provider stack (COV-11 technical note).
 */
function routerAt(hash: string): ({ children }: { children: ReactNode }) => ReactNode {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <MemoryRouter initialEntries={[`/roadmaps/x${hash}`]}>{children}</MemoryRouter>
  }
}

/** Append a target element carrying `id` to the document; removed on cleanup. */
function mountTarget(id: string): HTMLElement {
  const element = document.createElement('div')
  element.id = id
  document.body.append(element)
  return element
}

let scrollSpy: MockInstance<Element['scrollIntoView']>

beforeEach(() => {
  // `scrollIntoView` is polyfilled to a no-op in setup.ts (jsdom lacks it); spy
  // on the prototype so calls from any element instance are observed.
  scrollSpy = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {})
})

afterEach(() => {
  scrollSpy.mockRestore()
  document.body.innerHTML = ''
})

describe('useHashScroll', () => {
  it('scrolls the hash target into view when enabled and the element exists', () => {
    const target = mountTarget('sub_hashing')
    renderHook(() => useHashScroll(true), { wrapper: routerAt('#sub_hashing') })

    expect(scrollSpy).toHaveBeenCalledTimes(1)
    expect(scrollSpy).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
    // Called on the matching element, not some other node.
    expect(scrollSpy.mock.instances[0]).toBe(target)
  })

  it('is a no-op when disabled, even if the hash target exists', () => {
    mountTarget('sub_hashing')
    renderHook(() => useHashScroll(false), { wrapper: routerAt('#sub_hashing') })

    expect(scrollSpy).not.toHaveBeenCalled()
  })

  it('is a no-op when the hash target is missing', () => {
    // No element with this id is mounted (e.g. hidden by a filter).
    renderHook(() => useHashScroll(true), { wrapper: routerAt('#not_present') })

    expect(scrollSpy).not.toHaveBeenCalled()
  })
})
