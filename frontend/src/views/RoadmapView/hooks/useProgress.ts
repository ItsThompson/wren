import { useCallback, useEffect, useMemo, useState } from 'react'

import { createSessionClient } from '@/auth/createSessionClient'

/**
 * Fetch and mutate the caller's progress for one published roadmap (section 10
 * "Data fetching", section 06/07 progress endpoints). Uses the session-aware
 * client (credentials + transparent refresh), so the record resolves for the
 * signed-in user and is scoped to them server-side.
 *
 * The detailed snapshot seeds `checkedIds` and the per-user `deadline` on mount,
 * and `GET /next` seeds the current "next" subsection (highlighted in the list
 * view). `toggle` optimistically reflects the check/uncheck locally (so the bars
 * and done-state update instantly), persists the explicit-set via `POST /progress`,
 * and reconciles to the server's returned `checked_ids` and fresh `next`; a
 * failed write reverts the optimistic change. `setDeadline` mirrors this for the
 * countdown: it optimistically updates the local deadline, persists via
 * `PUT /deadline` (a date sets it, null clears it), and reverts on failure.
 * `baseUrl` is injected (defaulting at the view) so tests can point the client
 * at an MSW server.
 */
export function useProgress(
  roadmapId: string,
  baseUrl: string,
): {
  checkedIds: Set<string>
  toggle: (itemId: string, checked: boolean) => void
  deadline: string | null
  setDeadline: (deadline: string | null) => void
  /** The current "next" subsection id (from `GET /next`), or null when done. */
  nextSubsectionId: string | null
} {
  const client = useMemo(() => createSessionClient(baseUrl), [baseUrl])
  const [checkedIds, setCheckedIds] = useState<Set<string>>(() => new Set())
  const [deadline, setDeadlineState] = useState<string | null>(null)
  const [nextSubsectionId, setNextSubsectionId] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setCheckedIds(new Set())
    setDeadlineState(null)
    setNextSubsectionId(null)

    void (async () => {
      try {
        const { data } = await client.GET('/roadmaps/{roadmap_id}/progress', {
          params: { path: { roadmap_id: roadmapId }, query: { detailed: true } },
        })
        if (!active || !data) return
        if (data.checked_ids) setCheckedIds(new Set(data.checked_ids))
        setDeadlineState(data.deadline ?? null)
      } catch {
        // A read failure just leaves an unstarted checklist; not fatal.
      }
    })()

    void (async () => {
      try {
        const { data } = await client.GET('/roadmaps/{roadmap_id}/next', {
          params: { path: { roadmap_id: roadmapId } },
        })
        if (!active || !data) return
        setNextSubsectionId(data.items?.[0]?.subsection_id ?? null)
      } catch {
        // No next suggestion available; the list view simply highlights nothing.
      }
    })()

    return () => {
      active = false
    }
  }, [client, roadmapId])

  const toggle = useCallback(
    (itemId: string, checked: boolean) => {
      setCheckedIds((prev) => {
        const next = new Set(prev)
        if (checked) next.add(itemId)
        else next.delete(itemId)
        return next
      })
      void (async () => {
        try {
          const { data } = await client.POST('/roadmaps/{roadmap_id}/progress', {
            params: { path: { roadmap_id: roadmapId } },
            body: { item_ids: [itemId], state: checked ? 'complete' : 'incomplete' },
          })
          const serverIds = data?.progress.checked_ids
          if (serverIds) setCheckedIds(new Set(serverIds))
          if (data) setNextSubsectionId(data.next.items?.[0]?.subsection_id ?? null)
        } catch {
          // Revert the optimistic change so the UI matches the server.
          setCheckedIds((prev) => {
            const reverted = new Set(prev)
            if (checked) reverted.delete(itemId)
            else reverted.add(itemId)
            return reverted
          })
        }
      })()
    },
    [client, roadmapId],
  )

  const setDeadline = useCallback(
    (next: string | null) => {
      const previous = deadline
      setDeadlineState(next)
      void (async () => {
        try {
          const { data } = await client.PUT('/roadmaps/{roadmap_id}/deadline', {
            params: { path: { roadmap_id: roadmapId } },
            body: { deadline: next },
          })
          if (data) setDeadlineState(data.deadline ?? null)
        } catch {
          // Revert the optimistic change so the UI matches the server.
          setDeadlineState(previous)
        }
      })()
    },
    [client, roadmapId, deadline],
  )

  return { checkedIds, toggle, deadline, setDeadline, nextSubsectionId }
}
