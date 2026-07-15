import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'

import { createSessionClient } from '@/auth/createSessionClient'
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
 * Fetch one roadmap by ID for the owner and drive its publish action (section 10
 * "RoadmapView owns roadmap fetch"; section 06 `:publish`). Uses the
 * session-aware client (credentials + transparent refresh), so a private draft
 * resolves for its owner and returns 404/403 to anyone else.
 *
 * `state` is the fetch state; `publishState` is the publish sub-state (kept
 * separate so a blocked/failed publish never conflicts with the loaded roadmap).
 * A successful publish replaces the loaded roadmap with the returned published
 * one, so the view reflects the immutable published state without a refetch.
 *
 * `baseUrl` is injected (defaulting at the view) so tests can point the client at
 * an MSW server without touching global config.
 */
export function useRoadmap(
  roadmapId: string,
  baseUrl: string,
): {
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
  const client = useMemo(() => createSessionClient(baseUrl), [baseUrl])
  const navigate = useNavigate()
  const [state, setState] = useState<RoadmapViewState>({ phase: 'loading' })
  const [publishState, setPublishState] = useState<PublishState>({ phase: 'idle' })
  const [metadataState, setMetadataState] = useState<MetadataEditState>({ phase: 'idle' })
  const [forkState, setForkState] = useState<ForkState>({ phase: 'idle' })
  const [conflict, setConflict] = useState<Problem | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    let active = true
    setState({ phase: 'loading' })
    setPublishState({ phase: 'idle' })
    setMetadataState({ phase: 'idle' })
    setForkState({ phase: 'idle' })
    setConflict(null)

    void (async () => {
      try {
        const { data, response } = await client.GET('/roadmaps/{roadmap_id}', {
          params: { path: { roadmap_id: roadmapId } },
        })
        if (!active) return
        setState(
          data ? { phase: 'loaded', roadmap: data } : { phase: 'error', status: response.status },
        )
      } catch {
        // Network failure / no reachable backend: surface an error state rather
        // than hang on the loading skeleton.
        if (active) setState({ phase: 'error', status: null })
      }
    })()

    return () => {
      active = false
    }
  }, [client, roadmapId, reloadToken])

  const publish = useCallback(async () => {
    setPublishState({ phase: 'publishing' })
    try {
      const { data, error, response } = await client.POST('/roadmaps/{roadmap_id}:publish', {
        params: { path: { roadmap_id: roadmapId } },
      })
      if (data) {
        // Published: reflect the immutable transition in the loaded roadmap.
        setState({ phase: 'loaded', roadmap: data })
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
  }, [client, roadmapId])

  const editMetadata = useCallback(
    async (draft: MetadataDraft): Promise<boolean> => {
      // Presentation-only edit (title/description/subject_tags): not If-Match
      // guarded and never bumps the structural revision. On success
      // the returned roadmap replaces the loaded one so the header updates in
      // place; a 409 (a smuggled structural field on a published roadmap) surfaces
      // the shared conflict prompt, and any other failure a retry message.
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
          setState({ phase: 'loaded', roadmap: data })
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
    [client, roadmapId],
  )

  const fork = useCallback(() => {
    // Fork any readable roadmap (own or public) into a fresh private draft, then
    // navigate to it so the owner can edit and publish the copy.
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

  // Web-only lifecycle (visibility / archive / delete): a visibility toggle or
  // archive replaces the loaded roadmap in place; a successful delete leaves the
  // now-removed roadmap's route for the landing page.
  const onLifecycleChanged = useCallback(
    (roadmap: Roadmap) => setState({ phase: 'loaded', roadmap }),
    [],
  )
  const onDeleted = useCallback(() => navigate('/'), [navigate])
  const lifecycle = useLifecycle(client, roadmapId, {
    onChanged: onLifecycleChanged,
    onDeleted,
  })

  const reload = useCallback(() => setReloadToken((token) => token + 1), [])

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
