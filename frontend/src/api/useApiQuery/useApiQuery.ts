import useSWR, { type SWRConfiguration, type SWRResponse } from 'swr'

import type { Problem } from '@/lib/problem'

import { useSessionClient } from '../ApiClientContext'
import type { SessionClient } from '../client'
import { runQuery, type OpenApiResultBase, type SuccessData } from '../fetcher'
import type { ApiKey } from '../keys'

/** A typed `openapi-fetch` call bound to the session client. */
type ApiCall<R extends OpenApiResultBase> = (client: SessionClient) => Promise<R>

/**
 * SWR read bound to the shared session client (every authenticated read except
 * the public `useProfile`). The abstraction this epic exists to create: the
 * `key` carries cache identity, the `call` thunk carries the response typing
 * inferred from the path literal, and `runQuery` supplies the throw-adapter.
 *
 * A `null` key disables the fetch (SWR's enabled-gating idiom): no request, no
 * loading churn. Because `call` invokes `client.GET` on the shared session
 * client, the 401→refresh→retry middleware still fires and coalesces across
 * co-mounted reads. `error` is a `Problem`; `data` is inferred from the schema.
 */
export function useApiQuery<R extends OpenApiResultBase>(
  key: ApiKey | null,
  call: ApiCall<R>,
  options?: SWRConfiguration<SuccessData<R>, Problem>,
): SWRResponse<SuccessData<R>, Problem> {
  const client = useSessionClient()
  return useSWR<SuccessData<R>, Problem>(key, () => runQuery(() => call(client)), options)
}
