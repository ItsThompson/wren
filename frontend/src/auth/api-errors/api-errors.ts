import type { AuthResult } from '../types'

/**
 * The subset of the RFC 9457 problem+json body the auth forms use:
 * a human `detail`/`title` and an optional field-level map. Other members
 * (type/status/code) are ignored here.
 */
interface ProblemDetail {
  title?: string
  detail?: string
  fields?: Record<string, string>
}

const FALLBACK_MESSAGE = 'Something went wrong. Please try again.'

/**
 * Turn an openapi-fetch error body into a failed :type:`AuthResult`.
 *
 * The backend renders every error as problem+json, so the parsed error body
 * carries `detail` and, for conflicts/validation, a `fields` map. A malformed
 * or empty body degrades to a generic message rather than surfacing `undefined`.
 */
export function toAuthResult(error: unknown): AuthResult {
  const problem = (error ?? {}) as ProblemDetail
  const message = problem.detail ?? problem.title ?? FALLBACK_MESSAGE
  return { ok: false, message, fields: problem.fields }
}
