import useSWR, { type SWRConfiguration, type SWRResponse } from 'swr'

import type { Problem } from '@/lib/problem'

import { usePublicClient } from './ApiClientContext'
import type { ApiClient } from './client'
import { runQuery, type OpenApiResultBase, type SuccessData } from './fetcher'
import type { ApiKey } from './keys'

/** A typed `openapi-fetch` call bound to the public (credential-free) client. */
type PublicApiCall<R extends OpenApiResultBase> = (client: ApiClient) => Promise<R>

/**
 * SWR read bound to the shared public client. Identical key/call/options/return
 * shape to {@link useApiQuery}; kept as a distinct hook rather than an `{ auth }`
 * flag because only one read is public (`useProfile`) and specific interfaces
 * beat a generic mode toggle.
 */
export function usePublicApiQuery<R extends OpenApiResultBase>(
  key: ApiKey | null,
  call: PublicApiCall<R>,
  options?: SWRConfiguration<SuccessData<R>, Problem>,
): SWRResponse<SuccessData<R>, Problem> {
  const client = usePublicClient()
  return useSWR<SuccessData<R>, Problem>(key, () => runQuery(() => call(client)), options)
}
