import { useCallback, useEffect, useMemo, useState } from 'react'

import { createSessionClient } from '@/auth/createSessionClient'

/**
 * Fetch and mutate the caller's progress for one published roadmap (section 10
 * "Data fetching", section 06/07 progress endpoints). Uses the session-aware
 * client (credentials + transparent refresh), so the record resolves for the
 * signed-in user and is scoped to them server-side.
 *
 * The detailed snapshot seeds `checkedIds` on mount. `toggle` optimistically
 * reflects the check/uncheck locally (so the bars and done-state update
 * instantly), persists the explicit-set via `POST /progress`, and reconciles to
 * the server's returned `checked_ids`; a failed write reverts the optimistic
 * change. `baseUrl` is injected (defaulting at the view) so tests can point the
 * client at an MSW server.
 */
export function useProgress(
  roadmapId: string,
  baseUrl: string,
): { checkedIds: Set<string>; toggle: (itemId: string, checked: boolean) => void } {
  const client = useMemo(() => createSessionClient(baseUrl), [baseUrl])
  const [checkedIds, setCheckedIds] = useState<Set<string>>(() => new Set())

  useEffect(() => {
    let active = true
    setCheckedIds(new Set())

    void (async () => {
      try {
        const { data } = await client.GET('/roadmaps/{roadmap_id}/progress', {
          params: { path: { roadmap_id: roadmapId }, query: { detailed: true } },
        })
        if (active && data?.checked_ids) setCheckedIds(new Set(data.checked_ids))
      } catch {
        // A read failure just leaves an unstarted checklist; not fatal.
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

  return { checkedIds, toggle }
}
