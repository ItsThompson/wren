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

  it('mixes the hue into card for background and into foreground for text', () => {
    const style = styleOf('graphs')
    const hue = colorForTag('graphs') // #B8862F
    expect(style.backgroundColor).toBe(`color-mix(in oklab, ${hue} 16%, var(--card))`)
    expect(style.color).toBe(`color-mix(in oklab, ${hue} 72%, var(--foreground))`)
  })

  it('is stable: the same tag always yields the same style', () => {
    expect(tagPillStyle('recursion')).toEqual(tagPillStyle('recursion'))
  })

  it('gives different tags whose hues differ a different background', () => {
    // 'recursion' -> #B06A43 (index 0), 'arrays' -> #B05A72 (index 8).
    expect(styleOf('recursion').backgroundColor).not.toBe(styleOf('arrays').backgroundColor)
  })
})
