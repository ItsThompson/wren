export type ApiFailureKind = 'expected' | 'server' | 'network'

export interface ApiFailureInput {
  status: number | null
  error?: unknown
}

export function classifyApiFailure({ status, error }: ApiFailureInput): ApiFailureKind {
  if (status === null || error !== undefined && status === 0) return 'network'
  if (status >= 500) return 'server'
  return 'expected'
}

export function isReportableApiFailure(input: ApiFailureInput): boolean {
  return classifyApiFailure(input) !== 'expected'
}
