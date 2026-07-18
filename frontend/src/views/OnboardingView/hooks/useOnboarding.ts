import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router'

import { useSessionClient } from '@/api'
import { useAuth } from '@/auth'

import { STEPS } from '../steps'
import type { OnboardingActions, OnboardingState } from '../types'

/** Inline message shown on the step when completion fails; the user can retry. */
const COMPLETION_ERROR = "Couldn't finish setup. Please try again."

/**
 * The completion call's internal state, as a discriminated union so the
 * observable `phase`/`error` derive from one value and an impossible
 * "submitting with an error still set" combination cannot arise.
 */
type Completion =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'error'; message: string }

/**
 * The onboarding state machine: owns the current step index and the completion
 * call, exposing `{ state, actions }`. `next`/`back` clamp to the bounds of the
 * ordered {@link STEPS} list; `skip` and final-step `submit` share one
 * `complete()` terminal path.
 *
 * `complete()` posts to the shared session client (so it participates in the
 * app's 401→refresh→retry lock), then on success applies the returned user to
 * auth state **before** navigating. That ordering is the mechanism that prevents
 * the redirect loop: navigating against stale auth state would let the route
 * guard bounce the just-onboarded user back into onboarding. On failure it stays
 * on the step, surfaces an inline error, logs the failure, and does not apply the
 * user or navigate (the flag stays `false`, so a retry is safe).
 *
 * `useSessionClient`, `auth.applyUser`, and router `navigate` are all resolved
 * from context/router, so the hook is testable headlessly with a mock client, a
 * spy `applyUser`, and a spy `navigate`.
 */
export function useOnboarding(): { state: OnboardingState; actions: OnboardingActions } {
  const client = useSessionClient()
  const { applyUser } = useAuth()
  const navigate = useNavigate()

  const [stepIndex, setStepIndex] = useState(0)
  const [completion, setCompletion] = useState<Completion>({ status: 'idle' })

  const stepCount = STEPS.length

  const next = useCallback(() => {
    setStepIndex((index) => Math.min(index + 1, STEPS.length - 1))
  }, [])

  const back = useCallback(() => {
    setStepIndex((index) => Math.max(index - 1, 0))
  }, [])

  const complete = useCallback(async () => {
    setCompletion({ status: 'submitting' })
    try {
      const { data, response } = await client.POST('/me/onboarding:complete')
      if (data) {
        // Apply the fresh user (flag now true) BEFORE navigating so the guard
        // sees the updated flag and does not bounce back to onboarding.
        applyUser(data)
        navigate('/dashboard', { replace: true })
        return
      }
      console.error(`Onboarding completion failed (${response.status})`)
      setCompletion({ status: 'error', message: COMPLETION_ERROR })
    } catch (cause) {
      console.error('Onboarding completion failed', cause)
      setCompletion({ status: 'error', message: COMPLETION_ERROR })
    }
  }, [client, applyUser, navigate])

  const runComplete = useCallback(() => {
    void complete()
  }, [complete])

  const state: OnboardingState = {
    stepIndex,
    stepCount,
    isFirstStep: stepIndex === 0,
    isLastStep: stepIndex === stepCount - 1,
    phase: completion.status,
    error: completion.status === 'error' ? completion.message : null,
  }

  const actions: OnboardingActions = {
    next,
    back,
    // Skip and final-step submit are the same terminal path (no data collected,
    // so "skip with a sane default" degenerates to "end onboarding now").
    skip: runComplete,
    submit: runComplete,
  }

  return { state, actions }
}
