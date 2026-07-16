import { cn } from './utils'

/**
 * `cn` is the shared className combiner used across every component: it runs
 * inputs through clsx (conditional/array/object forms) and then twMerge, which
 * resolves conflicting Tailwind utilities so the last one wins. These cases lock
 * in both halves of that contract.
 */
describe('cn', () => {
  it('joins plain class strings', () => {
    expect(cn('px-2', 'font-bold')).toBe('px-2 font-bold')
  })

  it('drops falsy conditional values (clsx)', () => {
    const isActive = false
    const isDisabled = true
    expect(cn('base', isActive && 'active', isDisabled && 'disabled')).toBe('base disabled')
    expect(cn('a', null, undefined, false, 'b')).toBe('a b')
  })

  it('applies object and array class forms (clsx)', () => {
    expect(cn({ active: true, disabled: false })).toBe('active')
    expect(cn(['px-2', 'py-1'], { 'text-sm': true })).toBe('px-2 py-1 text-sm')
  })

  it('resolves conflicting Tailwind utilities so the last wins (twMerge)', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4')
    expect(cn('text-red-500', 'text-blue-500')).toBe('text-blue-500')
    expect(cn('p-4', 'p-2')).toBe('p-2')
  })

  it('merges conditional and conflicting classes together', () => {
    const isWide = true
    expect(cn('px-2 py-1', isWide && 'px-4')).toBe('py-1 px-4')
  })
})
