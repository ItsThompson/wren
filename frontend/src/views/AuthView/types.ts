/**
 * Submission state shared by the two auth forms (login + register).
 *
 * The `submitting` + `error` + field-error trio is always set together and
 * forms a submission status machine, so it is modeled as a single
 * discriminated union to keep impossible combinations unrepresentable
 * (frontend state-structure rule). Each form keeps its own `values` object,
 * which is a separate grouped concern.
 */
export type SubmitStatus =
  | { phase: 'idle' }
  | { phase: 'submitting' }
  | { phase: 'error'; message: string; fields: Record<string, string> }
