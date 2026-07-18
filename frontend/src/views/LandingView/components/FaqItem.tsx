import type { FaqItemData } from '../types'

interface FaqItemProps {
  item: FaqItemData
}

/** One FAQ entry: a left-aligned question with a plain-language answer. */
export function FaqItem({ item }: FaqItemProps) {
  return (
    <div className="border-t border-border py-6">
      <h3 className="text-lg font-semibold text-foreground">{item.question}</h3>
      <p className="mt-2 max-w-[64ch] leading-relaxed text-muted-foreground">{item.answer}</p>
    </div>
  )
}
