import { describe, expect, it } from 'vitest'

import {
  hasViolations,
  isImmutable,
  isStaleRevision,
  PROBLEM_CODE,
  toProblem,
  type Problem,
} from './problem'

/** The 409 stale-revision problem+json body the backend emits (spec section 06). */
function staleBody() {
  return {
    type: 'https://usewren.com/errors/stale-revision',
    title: 'Conflict with the current state',
    status: 409,
    code: PROBLEM_CODE.StaleRevision,
    detail: 'Roadmap revision changed; re-read and retry.',
    instance: '/roadmaps/dsa-7f3k',
  }
}

describe('toProblem', () => {
  it('maps a parsed problem body and prefers the response status', () => {
    const problem = toProblem(staleBody(), { status: 409 })
    expect(problem).toEqual<Problem>({
      status: 409,
      type: 'https://usewren.com/errors/stale-revision',
      title: 'Conflict with the current state',
      code: 'STALE_REVISION',
      detail: 'Roadmap revision changed; re-read and retry.',
      instance: '/roadmaps/dsa-7f3k',
      fields: undefined,
      violations: undefined,
    })
  })

  it('carries the field map and violations when present', () => {
    const problem = toProblem(
      {
        status: 422,
        code: 'VALIDATION',
        fields: { 'body.title': 'is required' },
        violations: [{ rule: 'V7_RESOURCE_REQUIRED', ids: ['sub_x'], message: 'no resources' }],
      },
      { status: 422 },
    )
    expect(problem.fields).toEqual({ 'body.title': 'is required' })
    expect(problem.violations).toHaveLength(1)
  })

  it('falls back to a null status when the request never resolved', () => {
    // A thrown network error passes no response and no parsed body.
    expect(toProblem(undefined).status).toBeNull()
    expect(toProblem(null, null).status).toBeNull()
  })

  it('reads the status from the body when no response is given', () => {
    expect(toProblem({ status: 404, code: 'NOT_FOUND' }).status).toBe(404)
  })
})

describe('problem classifiers', () => {
  it('detects a 409 stale revision only for the matching code', () => {
    expect(isStaleRevision(toProblem(staleBody(), { status: 409 }))).toBe(true)
    // A 409 with a different code (e.g. immutable) is not a stale revision.
    expect(isStaleRevision(toProblem({ code: 'IMMUTABLE' }, { status: 409 }))).toBe(false)
    // The right code but a non-409 status is not a stale revision either.
    expect(isStaleRevision(toProblem({ code: 'STALE_REVISION' }, { status: 422 }))).toBe(false)
  })

  it('detects a 409 immutable write', () => {
    expect(isImmutable(toProblem({ code: 'IMMUTABLE' }, { status: 409 }))).toBe(true)
    expect(isImmutable(toProblem({ code: 'DELETE_HAS_FOLLOWERS' }, { status: 409 }))).toBe(false)
  })

  it('detects a hard-block only when violations are present', () => {
    expect(
      hasViolations(
        toProblem({ violations: [{ rule: 'r', ids: [], message: 'm' }] }, { status: 422 }),
      ),
    ).toBe(true)
    expect(hasViolations(toProblem({ violations: [] }, { status: 422 }))).toBe(false)
    expect(hasViolations(toProblem({}, { status: 422 }))).toBe(false)
  })
})
