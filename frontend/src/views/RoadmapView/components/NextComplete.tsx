import { CircleCheck } from 'lucide-react'

/**
 * The calm `get_next` completion state (spec section 10; US-ERR-04): shown in the
 * list view once the learner has completed every item in the suggested path.
 * Quiet and encouraging (olive done-state, not a loud accent block), with meaning
 * carried by the check icon and the text, never color alone.
 */
export function NextComplete() {
  return (
    <div
      role="status"
      className="mt-6 flex items-center gap-3 rounded-lg border border-success/50 bg-success/10 p-4"
    >
      <CircleCheck aria-hidden className="size-5 shrink-0 text-success" />
      <div>
        <p className="font-medium text-foreground">You’re all caught up. Nice work.</p>
        <p className="text-sm text-muted-foreground">
          You’ve finished every step in the suggested path.
        </p>
      </div>
    </div>
  )
}
