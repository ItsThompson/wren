import { colorForTag, hashString, TAG_PALETTE } from './tag-color'

/**
 * The expected values below are the ground truth from the reference
 * algorithm (an independent oracle run), not values copied out of this module.
 * A regression in the hash or a reordered palette must break these assertions.
 */
describe('TAG_PALETTE', () => {
  it('has ten hues in the exact, unchanged order', () => {
    expect(TAG_PALETTE).toEqual([
      '#B06A43',
      '#B8862F',
      '#7E8A45',
      '#5E8C5A',
      '#3E8C82',
      '#4F7CA6',
      '#6A6DB0',
      '#8A5A96',
      '#B05A72',
      '#8A7F70',
    ])
  })
})

describe('hashString', () => {
  it('reproduces the reference hash for known strings', () => {
    expect(hashString('')).toBe(0)
    expect(hashString('a')).toBe(97)
    expect(hashString('arrays')).toBe(1409164998)
    expect(hashString('dynamic-programming')).toBe(441805899)
  })

  it('is deterministic for the same input', () => {
    expect(hashString('graphs')).toBe(hashString('graphs'))
  })
})

describe('colorForTag', () => {
  it('maps known tags to their stable hue', () => {
    // tag -> palette index (from the reference oracle):
    // recursion=0, graphs=1, concurrency=3, backtracking=4, trees=7, arrays=8,
    // dynamic-programming=9. Empty string hashes to 0 -> first hue.
    expect(colorForTag('recursion')).toBe('#B06A43')
    expect(colorForTag('graphs')).toBe('#B8862F')
    expect(colorForTag('concurrency')).toBe('#5E8C5A')
    expect(colorForTag('backtracking')).toBe('#3E8C82')
    expect(colorForTag('trees')).toBe('#8A5A96')
    expect(colorForTag('arrays')).toBe('#B05A72')
    expect(colorForTag('dynamic-programming')).toBe('#8A7F70')
    expect(colorForTag('')).toBe('#B06A43')
  })

  it('is deterministic and always returns a palette member', () => {
    for (const tag of ['sorting', 'hashing', 'greedy', 'systems-design']) {
      expect(colorForTag(tag)).toBe(colorForTag(tag))
      expect(TAG_PALETTE).toContain(colorForTag(tag))
    }
  })
})
