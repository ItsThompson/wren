import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { keys, useApiQuery, useSessionClient } from '@/api'
import { toProblem, type Problem } from '@/lib/problem'
import { useLifecycle } from './useLifecycle'
import type {
  ForkState,
  MetadataDraft,
  MetadataEditState,
  PublishState,
  Roadmap,
  RoadmapLifecycle,
  RoadmapViewState,
} from '../types'

/**
 * Map the SWR read result for `keys.roadmap(id)` into the view's semantic
 * {@link RoadmapViewState}. Guard-clause form (mirrors the pilot `useProfile`):
 * a background revalidation keeps the last-loaded roadmap on screen rather than
 * flashing the skeleton, and a read error preserves the HTTP status (or `null`
 * on a network failure) for `RoadmapErrorState`.
 */
function toRoadmapViewState(
  roadmap: Roadmap | undefined,
  error: Problem | undefined,
  isLoading: boolean,
): RoadmapViewState {
  if (isLoading && !roadmap) return { phase: 'loading' }
  if (error) return { phase: 'error', status: error.status }
  if (roadmap) return { phase: 'loaded', roadmap }
  return { phase: 'loading' }
}

/**
 * Fetch one roadmap by ID for the owner and drive its publish action
 * (`:publish`). The read derives from `useApiQuery(keys.roadmap(id))` on the
 * shared session client (credentials + transparent refresh), so a private draft
 * resolves for its owner and returns 404/403 to anyone else, and any co-mounted
 * reader of the same key (e.g. the tree route) shares one request and one cache
 * entry.
 *
 * `state` is the derived fetch state; `publishState`/`metadataState`/`forkState`/
 * `conflict` are local action sub-states (UI state, not cached data), kept
 * separate so a blocked/failed write never conflicts with the loaded roadmap. A
 * successful write reconciles the SWR cache in place
 * (`mutate(returned, { revalidate: false })`) so the view reflects the new state
 * without a refetch and without a stale flash.
 */
export function useRoadmap(roadmapId: string): {
  state: RoadmapViewState
  publishState: PublishState
  publish: () => Promise<void>
  metadataState: MetadataEditState
  editMetadata: (draft: MetadataDraft) => Promise<boolean>
  forkState: ForkState
  fork: () => void
  lifecycle: RoadmapLifecycle
  /** A 409 write conflict (stale/immutable) surfaced above the view, or null. */
  conflict: Problem | null
  /** Refetch the roadmap (the re-read recovery for a stale/immutable conflict). */
  reload: () => void
} {
  const navigate = useNavigate()
  const client = useSessionClient()
  const {
    data: roadmap,
    error: readError,
    isLoading,
    mutate,
  } = useApiQuery(keys.roadmap(roadmapId), (sessionClient) =>
    sessionClient.GET('/roadmaps/{roadmap_id}', { params: { path: { roadmap_id: roadmapId } } }),
  )

  const [publishState, setPublishState] = useState<PublishState>({ phase: 'idle' })
  const [metadataState, setMetadataState] = useState<MetadataEditState>({ phase: 'idle' })
  const [forkState, setForkState] = useState<ForkState>({ phase: 'idle' })
  const [conflict, setConflict] = useState<Problem | null>(null)

  const state = toRoadmapViewState(roadmap, readError, isLoading)

  // Sub-state reset invariant (R2). React Router keeps the same RoadmapView
  // instance mounted across a `:roadmapId` change (fork -> navigate, or
  // navigating between roadmaps), so these plain-`useState` sub-states would
  // otherwise leak from roadmap A onto roadmap B. The read effect that used to
  // reset them is gone (the read is now derived from `useApiQuery`), so the
  // reset is re-homed here, keyed on `roadmapId`.
  useEffect(() => {
    setPublishState({ phase: 'idle' })
    setMetadataState({ phase: 'idle' })
    setForkState({ phase: 'idle' })
    setConflict(null)
  }, [roadmapId])

  const publish = useCallback(async () => {
    setPublishState({ phase: 'publishing' })
    try {
      const { data, error, response } = await client.POST('/roadmaps/{roadmap_id}:publish', {
        params: { path: { roadmap_id: roadmapId } },
      })
      if (data) {
        // Published: write the immutable transition into the cache in place so
        // the view reflects it without a refetch.
        void mutate(data, { revalidate: false })
        setPublishState({ phase: 'idle' })
        return
      }
      const problem = toProblem(error, response)
      if (response.status === 422) {
        setPublishState({ phase: 'blocked', violations: problem.violations ?? [] })
        return
      }
      if (response.status === 409) {
        // Already published/archived (immutable) or the draft changed under us
        // (stale): surface the shared 409 re-read / fork-to-change prompt.
        setConflict(problem)
        setPublishState({ phase: 'idle' })
        return
      }
      setPublishState({ phase: 'failed', status: response.status })
    } catch {
      setPublishState({ phase: 'failed', status: null })
    }
  }, [client, roadmapId, mutate])

  const editMetadata = useCallback(
    async (draft: MetadataDraft): Promise<boolean> => {
      // Presentation-only edit (title/description/subject_tags): not If-Match
      // guarded and never bumps the structural revision. On success the returned
      // roadmap is written into the cache so the header updates in place; a 409
      // (a smuggled structural field on a published roadmap) surfaces the shared
      // conflict prompt, and any other failure a retry message.
      setMetadataState({ phase: 'saving' })
      try {
        const { data, error, response } = await client.PATCH('/roadmaps/{roadmap_id}/metadata', {
          params: { path: { roadmap_id: roadmapId } },
          body: {
            title: draft.title,
            description: draft.description,
            subject_tags: draft.subject_tags,
          },
        })
        if (data) {
          void mutate(data, { revalidate: false })
          setMetadataState({ phase: 'idle' })
          return true
        }
        if (response.status === 409) {
          setConflict(toProblem(error, response))
          setMetadataState({ phase: 'idle' })
          return false
        }
        setMetadataState({ phase: 'failed', status: response.status })
        return false
      } catch {
        setMetadataState({ phase: 'failed', status: null })
        return false
      }
    },
    [client, roadmapId, mutate],
  )

  const fork = useCallback(() => {
    // Fork any readable roadmap (own or public) into a fresh private draft, then
    // navigate to it so the owner can edit and publish the copy. The fork is a
    // new resource, so there is no cache write here: navigating to its route
    // reads it under its own key.
    setForkState({ phase: 'forking' })
    void (async () => {
      try {
        const { data, response } = await client.POST('/roadmaps/{roadmap_id}:fork', {
          params: { path: { roadmap_id: roadmapId } },
        })
        if (data) {
          setForkState({ phase: 'idle' })
          navigate(`/roadmaps/${data.id}`)
          return
        }
        setForkState({ phase: 'failed', status: response.status })
      } catch {
        setForkState({ phase: 'failed', status: null })
      }
    })()
  }, [client, navigate, roadmapId])

  // Web-only lifecycle (visibility / archive / delete). A visibility toggle or
  // archive reconciles the shared roadmap cache in place (replacing the old
  // view `setState` callback), so the tree route and the roadmap route stay
  // coherent; a successful delete leaves the now-removed roadmap's route.
  const onLifecycleChanged = useCallback(
    (updated: Roadmap) => {
      void mutate(updated, { revalidate: false })
    },
    [mutate],
  )
  const onDeleted = useCallback(() => navigate('/'), [navigate])
  const lifecycle = useLifecycle(client, roadmapId, {
    onChanged: onLifecycleChanged,
    onDeleted,
  })

  const reload = useCallback(() => {
    void mutate()
  }, [mutate])

  return {
    state,
    publishState,
    publish,
    metadataState,
    editMetadata,
    forkState,
    fork,
    lifecycle,
    conflict,
    reload,
  }
}
