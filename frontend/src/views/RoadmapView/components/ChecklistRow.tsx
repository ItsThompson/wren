import type { ChecklistItem } from '../types'

interface ChecklistRowProps {
  item: ChecklistItem
  checked: boolean
  onToggle: (checked: boolean) => void
}

/**
 * An interactive checklist row: an olive-accented
 * checkbox and the item text. Checked rows get the olive fill plus a
 * `muted-foreground` strikethrough label, so done-state is conveyed by more than
 * color (checkbox state + strikethrough + text). Toggling calls `onToggle`,
 * which the list view persists via `progress_update`.
 */
export function ChecklistRow({ item, checked, onToggle }: ChecklistRowProps) {
  return (
    <li>
      <label className="flex cursor-pointer items-start gap-2 rounded-md py-1.5 text-sm hover:bg-muted/60">
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => onToggle(event.target.checked)}
          className="mt-0.5 size-4 shrink-0 rounded accent-[var(--success)]"
        />
        <span className={checked ? 'text-muted-foreground line-through' : 'text-foreground'}>
          {item.text}
        </span>
      </label>
    </li>
  )
}
