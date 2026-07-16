import { toAuthResult } from './api-errors'

/** Mirrors the private `FALLBACK_MESSAGE` in `api-errors.ts`. */
const FALLBACK_MESSAGE = 'Something went wrong. Please try again.'

describe('toAuthResult', () => {
  it('uses the problem detail as the message and passes fields through', () => {
    const result = toAuthResult({
      detail: 'An account with this email already exists.',
      fields: { email: 'This email is already registered.' },
    })

    expect(result).toEqual({
      ok: false,
      message: 'An account with this email already exists.',
      fields: { email: 'This email is already registered.' },
    })
  })

  it('falls back to the title when no detail is present', () => {
    const result = toAuthResult({ title: 'Conflict' })

    expect(result).toEqual({ ok: false, message: 'Conflict', fields: undefined })
  })

  it('degrades to a generic message for an empty body', () => {
    const result = toAuthResult({})

    expect(result).toEqual({ ok: false, message: FALLBACK_MESSAGE, fields: undefined })
  })

  it('degrades to a generic message when the error is null or undefined', () => {
    expect(toAuthResult(null)).toEqual({ ok: false, message: FALLBACK_MESSAGE, fields: undefined })
    expect(toAuthResult(undefined)).toEqual({
      ok: false,
      message: FALLBACK_MESSAGE,
      fields: undefined,
    })
  })
})
