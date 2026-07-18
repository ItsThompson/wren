import { FAQ_ITEMS } from '../constants'
import { FaqItem } from './FaqItem'

/** Frequently asked questions: plain answers, no external links. */
export function FaqSection() {
  return (
    <section>
      <h2 className="text-2xl font-semibold text-foreground">Questions</h2>
      <div className="mt-4">
        {FAQ_ITEMS.map((item) => (
          <FaqItem key={item.question} item={item} />
        ))}
      </div>
    </section>
  )
}
