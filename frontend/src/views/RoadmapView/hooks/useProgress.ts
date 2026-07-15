import { useCallback, useEffect, useMemo, useState } from 'react'

import { createSessionClient } from '@/auth/createSessionClient'
import { isStaleRevision, toProblem } from '@/lib/problem'
import type { ProgressNotice } from '../types'

/**
 * Fetch and mutate the caller's progress for one published roadmap (section 10
 * "Data fetching", section 06/07 progress endpoints). Uses the session-aware
 * client (credentials + transparent refresh), so the record resolves for the
 * signed-in user and is scoped to them server-side.
 *
 * The detailed snapshot seeds `checkedIds` and the per-user `deadline` on mount,
 * and `GET /next` seeds the current "next" subsection (highlighted in the list
 * view) plus the `complete` flag (the calm all-caught-up state). `toggle`
 * optimistically reflects the check/uncheck locally (so the bars and done-state
 * update instantly), persists the explicit-set via `POST /progress`, and
 * reconciles to the server's returned `checked_ids` and fresh `next`. A failed
 * write reverts the optimistic change and surfaces a `notice` (a 409 becomes the
 * stale re-read prompt; anything else a quiet inline notice) instead of failing
 * silently. `setDeadline` mirrors this for the countdown, and
 * `reload` refetches everything for the re-read recovery. `baseUrl` is injected
 * (defaulting at the view) so tests can point the client at an MSW server.
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
  /** True once the caller has completed every item in the suggested path. */
  nextComplete: boolean
  /** A surfaced write failure, or null; cleared by `dismissNotice` / `reload`. */
  notice: ProgressNotice | null
  dismissNotice: () => void
  /** Refetch progress + next (the re-read recovery for a stale write). */
  reload: () => void
} {
  const client = useMemo(() => createSessionClient(baseUrl), [baseUrl])
  const [checkedIds, setCheckedIds] = useState<Set<string>>(() => new Set())
  const [deadline, setDeadlineState] = useState<string | null>(null)
  const [nextSubsectionId, setNextSubsectionId] = useState<string | null>(null)
  const [nextComplete, setNextComplete] = useState(false)
  const [notice, setNotice] = useState<ProgressNotice | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    let active = true
    setCheckedIds(new Set())
    setDeadlineState(null)
    setNextSubsectionId(null)
    setNextComplete(false)
    setNotice(null)

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
        setNextComplete(data.complete)
      } catch {
        // No next suggestion available; the list view simply highlights nothing.
      }
    })()

    return () => {
      active = false
    }
  }, [client, roadmapId, reloadToken])

  const toggle = useCallback(
    (itemId: string, checked: boolean) => {
      const revert = () =>
        setCheckedIds((prev) => {
          const reverted = new Set(prev)
          if (checked) reverted.delete(itemId)
          else reverted.add(itemId)
          return reverted
        })

      setCheckedIds((prev) => {
        const next = new Set(prev)
        if (checked) next.add(itemId)
        else next.delete(itemId)
        return next
      })
      setNotice(null)

      void (async () => {
        try {
          const { data, error, response } = await client.POST('/roadmaps/{roadmap_id}/progress', {
            params: { path: { roadmap_id: roadmapId } },
            body: { item_ids: [itemId], state: checked ? 'complete' : 'incomplete' },
          })
          if (data) {
            if (data.progress.checked_ids) setCheckedIds(new Set(data.progress.checked_ids))
            setNextSubsectionId(data.next.items?.[0]?.subsection_id ?? null)
            setNextComplete(data.next.complete)
            return
          }
          // An HTTP error response (409/422/5xx): revert and surface it. A stale
          // revision is the re-read prompt; anything else a quiet inline notice.
          revert()
          setNotice(isStaleRevision(toProblem(error, response)) ? { kind: 'stale' } : { kind: 'save-failed' })
        } catch {
          // Network failure: revert and surface the quiet save-failed notice.
          revert()
          setNotice({ kind: 'save-failed' })
        }
      })()
    },
    [client, roadmapId],
  )

  const setDeadline = useCallback(
    (next: string | null) => {
      const previous = deadline
      setDeadlineState(next)
      setNotice(null)
      void (async () => {
        try {
          const { data, error, response } = await client.PUT('/roadmaps/{roadmap_id}/deadline', {
            params: { path: { roadmap_id: roadmapId } },
            body: { deadline: next },
          })
          if (data) {
            setDeadlineState(data.deadline ?? null)
            return
          }
          // HTTP error response: revert and surface it, mirroring the toggle path
          // so both write paths announce failures instead of reverting silently.
          setDeadlineState(previous)
          setNotice(isStaleRevision(toProblem(error, response)) ? { kind: 'stale' } : { kind: 'save-failed' })
        } catch {
          // Network failure: revert and surface the quiet save-failed notice.
          setDeadlineState(previous)
          setNotice({ kind: 'save-failed' })
        }
      })()
    },
    [client, roadmapId, deadline],
  )

  const dismissNotice = useCallback(() => setNotice(null), [])
  const reload = useCallback(() => {
    setNotice(null)
    setReloadToken((token) => token + 1)
  }, [])

  return {
    checkedIds,
    toggle,
    deadline,
    setDeadline,
    nextSubsectionId,
    nextComplete,
    notice,
    dismissNotice,
    reload,
  }
}
