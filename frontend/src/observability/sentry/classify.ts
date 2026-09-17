export type ApiFailureKind = 'expected' | 'upstream' | 'network'

export interface ApiFailureInput {
  status: number | null
  error?: unknown
}

export function classifyApiFailure({ status, error }: ApiFailureInput): ApiFailureKind {
  if (status === null || (error !== undefined && status === 0)) return 'network'
  if (!Number.isInteger(status) || status < 100 || status > 599) return 'expected'
  if (status >= 500) return 'upstream'
  return 'expected'
}

export function isReportableApiFailure(input: ApiFailureInput): boolean {
  return classifyApiFailure(input) !== 'expected'
}
