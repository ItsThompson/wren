import { colorForTag } from '@/lib/tag-color'
import { tagPillStyle } from './tag-pill-style'

/** Read the style back as a plain string map for property-level assertions. */
function styleOf(tag: string): Record<string, string> {
  return tagPillStyle(tag) as unknown as Record<string, string>
}

describe('tagPillStyle', () => {
  it('exposes the tag hue from the shared palette as --tag-hue', () => {
    // 'arrays' hashes to palette index 8 (#B05A72) per the section-09 oracle.
    expect(styleOf('arrays')['--tag-hue']).toBe('#B05A72')
    expect(styleOf('arrays')['--tag-hue']).toBe(colorForTag('arrays'))
  })

  it('drives the color from --tag-hue via color-mix (the var is load-bearing)', () => {
    const style = styleOf('graphs')
    expect(style['--tag-hue']).toBe(colorForTag('graphs')) // #B8862F
    expect(style.backgroundColor).toBe('color-mix(in oklab, var(--tag-hue) 16%, var(--card))')
    expect(style.color).toBe('color-mix(in oklab, var(--tag-hue) 72%, var(--foreground))')
  })

  it('is stable: the same tag always yields the same style', () => {
    expect(tagPillStyle('recursion')).toEqual(tagPillStyle('recursion'))
  })

  it('gives different tags whose hues differ a different --tag-hue', () => {
    // 'recursion' -> #B06A43 (index 0), 'arrays' -> #B05A72 (index 8).
    expect(styleOf('recursion')['--tag-hue']).not.toBe(styleOf('arrays')['--tag-hue'])
  })
})
