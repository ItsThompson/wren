import type { components } from '@/api'

/** One structural rule failure from a publish hard-block (spec section 06). */
export type Violation = components['schemas']['Violation']

/**
 * The RFC 9457 `application/problem+json` body every Wren error renders (spec
 * section 06, backend `core/errors.py`). The generated client types error bodies
 * only as the default validation shape, so this is the canonical client-side
 * mirror of the backend `ProblemDetail` wire contract. `code` is the branch key:
 * `STALE_REVISION` -> re-read, `IMMUTABLE` -> fork-to-change, `VALIDATION` ->
 * violations / field map.
 */
export interface Problem {
  /** HTTP status, or null when the request never resolved (network failure). */
  status: number | null
  type?: string
  title?: string
  code?: string
  detail?: string
  instance?: string
  /** Field-level messages for a request-validation 422 (dotted field -> msg). */
  fields?: Record<string, string>
  /** Structural violations for a publish/validate hard-block. */
  violations?: Violation[]
}

/**
 * The machine-readable `code`s the write/lifecycle contract branches on (mirror
 * of the backend `ErrorCode`). Only the values the frontend acts on are listed.
 */
export const PROBLEM_CODE = {
  StaleRevision: 'STALE_REVISION',
  Immutable: 'IMMUTABLE',
  DeleteHasFollowers: 'DELETE_HAS_FOLLOWERS',
  Validation: 'VALIDATION',
} as const

/** The minimal `Response` surface `toProblem` reads (openapi-fetch returns one). */
interface ResponseLike {
  status: number
}

/**
 * Normalize an openapi-fetch error body + response into a {@link Problem}. The
 * backend renders every error as problem+json, so `error` is the parsed body;
 * the `response` supplies the authoritative status (and covers a null/empty body
 * from a bare 4xx/5xx). A network failure passes no response and yields a null
 * status, which callers treat as a generic "couldn't reach the server".
 */
export function toProblem(error: unknown, response?: ResponseLike | null): Problem {
  const body = (error ?? {}) as Partial<Problem>
  return {
    status: response?.status ?? body.status ?? null,
    type: body.type,
    title: body.title,
    code: body.code,
    detail: body.detail,
    instance: body.instance,
    fields: body.fields,
    violations: body.violations,
  }
}

/** A 409 optimistic-concurrency mismatch: the caller must re-read and retry. */
export const isStaleRevision = (problem: Problem): boolean =>
  problem.status === 409 && problem.code === PROBLEM_CODE.StaleRevision

/** A 409 write against a published/archived roadmap: fork to change instead. */
export const isImmutable = (problem: Problem): boolean =>
  problem.status === 409 && problem.code === PROBLEM_CODE.Immutable

/** A 422 (or validate) hard-block carrying at least one structural violation. */
export const hasViolations = (problem: Problem): boolean =>
  (problem.violations?.length ?? 0) > 0
